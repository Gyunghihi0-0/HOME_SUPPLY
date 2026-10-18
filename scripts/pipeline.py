"""Daily job: preserve verified output on source failure; publish atomically."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from scripts.collector import BOARD,KST,collect,status_at
from scripts.http_client import Client,SourceError
from scripts.apis import Applyhome,Molit,APPLY_SOURCE,TRADE_SOURCE,empty_unit,won
from scripts.analysis import calculate,months_before
from scripts.validate import validate,freshness
from scripts.matching import address_key,compact
from scripts.structured import normalize_type
from scripts.geocoding import VWorld
from scripts.kakao import Kakao

ROOT=Path(__file__).resolve().parents[1]

def load(path):return json.loads(path.read_text(encoding='utf-8'))

def source(ident,name,url,now,status='not_checked',previous=None,count=None,code=None):
    return dict(id=ident,name=name,url=url,status=status,checked_at=now.isoformat(),last_success_at=now.isoformat() if status=='ok' else (previous or {}).get('last_success_at'),
        error_code=code,message=code,records_count=count)

def merge(previous,items,now):
    import re
    def order(item):
        source=re.search(r'[?&]bIdx=(\d+)',item['notice_url'] or '')
        return item['notice_updated_at'] or '',int(source[1]) if source else 0
    result={}
    for new in sorted([deepcopy(x) for x in previous]+items,key=order):
        if new['id'] not in {p['id'] for p in previous} and new['address']:
            # A newly found older original must not rename an already published canonical id.
            established=[p for p in previous if compact(p['name'])==compact(new['name']) and address_key(p['address'])==address_key(new['address'])
                and order(new)<order(p) and any(h['change_type']=='correction' for h in p['notice_history'])
                and (not p['pblanc_no'] or not new['pblanc_no'] or p['pblanc_no']==new['pblanc_no'])]
            if len(established)==1:new=deepcopy(new);new['id']=established[0]['id']
        if new['id'] not in result:
            owners=[x for x in result.values() if any(h['notice_url']==new['notice_url'] for h in x['notice_history'])]
            if len(owners)==1:new=deepcopy(new);new['id']=owners[0]['id']
        # Exact address + exact project name only. Never merge a later supply round,
        # multi-block title, or an announcement whose address is missing.
        if new['id'] not in result and new['address'] and new['notice_history'][0]['change_type'] in ('correction','cancellation') and not any(x in new['name'] for x in ('추가','후속','재공급','재모집')):
            matches=[x for x in result.values() if address_key(x['address'])==address_key(new['address']) and compact(x['name'])==compact(new['name'])
                and (not x['pblanc_no'] or not new['pblanc_no'] or x['pblanc_no']==new['pblanc_no'])]
            if len(matches)==1:
                new=deepcopy(new);new['id']=matches[0]['id']
        old=result.get(new['id'])
        if old:
            hashes={h['content_sha256'] for h in old['notice_history']}
            additions=[deepcopy(h) for h in new['notice_history'] if h['content_sha256'] not in hashes]
            for h in additions:
                if h['change_type']=='initial' and any(prior['notice_url']==h['notice_url'] for prior in old['notice_history']):h['change_type']='changed'
            history=old['notice_history']+additions
            if order(new)<order(old):
                old['notice_history']=history
                continue
            new['notice_history']=history
            if new['notice_history'][-1]['change_type'] in ('correction','changed'):
                if 'application_schedule_postponed' not in new['collection_issues']:
                    for key in ('apply_start_at','apply_end_at'):
                        if new[key] is None:new[key]=old[key]
                    if old['apply_end_at'] and new['apply_end_at']==old['apply_end_at'] and new['deadline_note'] is None:
                        new['deadline_note']=old['deadline_note']
                if new['eligibility']['evidence_text'] is None:
                    new['eligibility']=deepcopy(old['eligibility'])
            # Unavailable enrichment is preserved until successful replacement.
            if not new['units']:new['units']=old['units']
            for key in ['housing_manage_no','pblanc_no']:
                if new[key] is None:new[key]=old[key]
            new['location_verified']=old['location_verified']
            if {k:v for k,v in new.items() if k!='updated_at'}=={k:v for k,v in old.items() if k!='updated_at'}:
                new['updated_at']=old['updated_at']
        result[new['id']]=new
    for item in result.values():
        item['status']=status_at(item['apply_start_at'],item['apply_end_at'],now,item['status']=='cancelled')
    return sorted(result.values(),key=lambda x:(x['notice_updated_at'] or '',x['id']),reverse=True)

def enrich(items,client,now,config,policy,apply_key,trade_key,apply_client=None,location_audit=None,diagnostics=None):
    apply=apply_client or Applyhome(client,apply_key); molit=Molit(client,trade_key,os.getenv('MOLIT_ALLOW_GENERAL_FALLBACK','').lower()=='true',general_key=os.getenv('MOLIT_GENERAL_SERVICE_KEY'))
    geo=Kakao(client,os.getenv('KAKAO_REST_API_KEY')) if os.getenv('KAKAO_REST_API_KEY') else VWorld(client,os.getenv('VWORLD_API_KEY'),os.getenv('VWORLD_DOMAIN'))
    price_error=None;trade_error=None;price_count=0;trade_count=0;trade_cache={};connected=0;geo_error=None
    for item in items:
        print('enrich_start: '+item['id'],flush=True)
        mapping=config['projects'].get(item['id'])
        discovered=None
        transient={'official_project_mapping_required','official_project_not_matched','official_project_not_unique','missing_applyhome_key',
            'missing_vworld_key','official_geocode_not_found','geocode_address_mismatch','api_application_error','network_error',
            'verified_target_location_required','target_build_year_uses_official_planned_move_year','disability_allocation_table_required',
            'some_comparison_locations_unverified','comparison_geocode_budget_reached'}
        item['collection_issues']=[x for x in item['collection_issues'] if x not in transient and not x.startswith(('vworld_','kakao_')) and x!='district_coverage_sampled']
        if not mapping:
            try:
                mapping,detail,models=apply.discover(item);discovered=(detail,models)
            except SourceError as exc:
                reason=str(exc);price_error=reason
                item['collection_issues']=sorted(set(item['collection_issues']+[reason]))
                continue
        if not mapping.get('evidence_url') or not mapping.get('official_address'):
            price_error='mapping_evidence_required';continue
        try:
            detail,models=discovered or apply.project(mapping)
            units=[]
            available=item['units']
            if not available:
                available=[empty_unit(str(m['MODEL_NO']),mapping.get('units',{}).get(str(m['MODEL_NO']),{}).get('area_sqm')) for m in models if str(m['MODEL_NO']) in mapping.get('units',{})]
            if not available:
                available=[empty_unit(str(m['HOUSE_TY'])) for m in models]
                item['collection_issues'].append('disability_allocation_table_required')
            for original in available:
                matches=[m for m in models if normalize_type(m.get('HOUSE_TY',''))==normalize_type(original['type_id']) and normalize_type(original['type_id']) is not None]
                kind=normalize_type(original['type_id'])
                if not matches and kind and not kind[1]:
                    candidates=[m for m in models if normalize_type(m.get('HOUSE_TY','')) and normalize_type(m['HOUSE_TY'])[0]==kind[0]]
                    if len(candidates)==1:matches=candidates
                if not matches:
                    matches=[m for m in models if str(m['MODEL_NO'])==original['type_id'] and str(m['MODEL_NO']) in mapping.get('units',{})]
                if len(matches)!=1:
                    units.append(dict(original,analysis_reason='unit_model_not_unique'));continue
                model=matches[0]
                unit=dict(original)
                unit_mapping=mapping.get('units',{}).get(str(model['MODEL_NO']))
                if unit_mapping:
                    if unit_mapping['house_ty']!=model['HOUSE_TY'] or not unit_mapping.get('evidence_url'):raise SourceError('unit_evidence_mismatch')
                    unit['area_sqm']=unit_mapping.get('area_sqm');unit['allocation_count']=unit_mapping.get('disability_allocation_count')
                if unit['area_sqm'] is not None:
                    import re
                    number=re.match(r'0*(\d+(?:\.\d+)?)',model['HOUSE_TY'])
                    if not number or abs(float(number[1])-unit['area_sqm'])>0.02:raise SourceError('exclusive_area_mismatch')
                unit.update(sale_price_krw=won(model.get('LTTOT_TOP_AMOUNT')),comparison_median_krw=None,
                    estimated_gap_krw=None,gap_rate_pct=None,comparables=[],comparables_count=0,confidence='unavailable')
                if unit['sale_price_krw']:
                    unit['sale_price_basis']='maximum_base_price';unit['sale_price_evidence_url']=APPLY_SOURCE
                unit['analysis_reason']='disability_allocation_unverified' if not unit['allocation_count'] else 'exclusive_area_unverified' if unit['area_sqm'] is None else 'verified_coordinates_pending'
                units.append(unit)
            if not units:raise SourceError('disability_allocation_table_required')
            connected+=1
            item.update(housing_manage_no=mapping['housing_manage_no'],pblanc_no=mapping['pblanc_no'],units=units,
                housing_type={'01':'private_apt','03':'public_apt'}.get(detail.get('HOUSE_DTL_SECD'),'unknown'))
            if any(u['sale_price_krw'] for u in units):price_count+=1
            if any(not u['sale_price_krw'] for u in units):price_error='some_unit_prices_unavailable'
        except Exception as exc:
            price_error=str(exc) if isinstance(exc,SourceError) else 'price_data_invalid'
            continue
        if not any(u['sale_price_krw'] and u['area_sqm'] and u['allocation_count'] for u in item['units']):
            continue
        target=mapping.get('location')
        if not target:
            try:
                target=geo.locate(item['address'])
                move=str(detail.get('MVN_PREARNGE_YM',''))
                target['build_year']=int(move[:4]) if move[:4].isdigit() else None
                target['district_prefixes']=geo.districts(target['coordinates'],policy['radius_m'])
                target['lawd_codes']=sorted(target['district_prefixes'])
                if getattr(geo,'coverage_complete',True) is False:
                    item['collection_issues'].append('district_coverage_sampled')
                item['collection_issues'].append('target_build_year_uses_official_planned_move_year')
            except SourceError as exc:
                target=None
                geo_error=str(exc)
                trade_error='verified_target_location_required'
                item['collection_issues']=sorted(set(item['collection_issues']+[str(exc)]))
        item['location_verified']=bool(target and target.get('coordinates') and target.get('evidence_url'))
        if item['location_verified'] and location_audit is not None:
            location_audit['targets'][item['id']]=dict(address=item['address'],coordinates=target['coordinates'],
                build_year=target.get('build_year'),lawd_codes=target.get('lawd_codes',[]),evidence_url=target['evidence_url'],checked_at=now.isoformat())
        if not target or not target.get('lawd_codes'):
            for unit in item['units']:
                if unit['analysis_reason']=='verified_coordinates_pending':unit['analysis_reason']='verified_coordinates_missing'
            trade_error=trade_error or 'verified_target_location_required';continue
        try:
            print('trade_start: '+item['id']+' districts='+','.join(target['lawd_codes']),flush=True)
            trades=[]
            day=months_before(now.date(),policy['maximum_months']).replace(day=1)
            while day<=now.date():
                for lawd in target['lawd_codes']:
                    cache_key=(lawd,day.strftime('%Y%m'))
                    if cache_key not in trade_cache:trade_cache[cache_key]=molit.month(*cache_key,now)
                    trades.extend(trade_cache[cache_key])
                day=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
            print('trade_loaded: '+item['id']+' records='+str(len(trades)),flush=True)
            locations=dict(config['trade_locations'])
            if geo.key and (target.get('district_prefix') or target.get('district_prefixes')):
                seen_locations=set()
                geocode_jobs=[]
                for t in trades:
                    # Geocode only plausible analysis candidates, not the whole district history.
                    if not any(u['area_sqm'] and abs(t['area_sqm']/u['area_sqm']-1)*100<=policy['area_tolerance_pct'] for u in item['units']):continue
                    if not target.get('build_year') or abs(t['build_year']-target['build_year'])>policy['build_year_tolerance']:continue
                    identity=t['location']+'|'+t['apartment_name']
                    if identity in locations or identity in seen_locations:continue
                    if len(seen_locations)>=500:
                        item['collection_issues'].append('comparison_geocode_budget_reached');break
                    seen_locations.add(identity)
                    code,dong,parcel=t['location'].split('|')
                    if code not in target['lawd_codes']:continue
                    prefix=target.get('district_prefixes',{}).get(code) or target.get('district_prefix')
                    if not prefix:continue
                    geocode_jobs.append((identity,prefix+' '+dong+' '+parcel))
                # Bounded concurrency avoids spending the whole daily budget on
                # serial lookups of distinct apartment addresses across districts.
                from concurrent.futures import ThreadPoolExecutor
                def locate_job(job):
                    identity,address=job
                    try:return identity,geo.locate(address)
                    except SourceError:return identity,None
                with ThreadPoolExecutor(max_workers=4) as workers:
                    for identity,loc in workers.map(locate_job,geocode_jobs):
                        if loc:locations[identity]=loc
                        else:item['collection_issues'].append('some_comparison_locations_unverified')
                print('trade_coordinates: '+item['id']+' requested='+str(len(geocode_jobs))+' verified='+str(len(locations)),flush=True)
            item['units']=[calculate(u,trades,target,locations,policy,now.date()) for u in item['units']]
            if 'comparison_geocode_budget_reached' in item['collection_issues']:
                trade_error='comparison_geocode_budget_reached'
                item['units']=[dict(u,comparison_median_krw=None,estimated_gap_krw=None,gap_rate_pct=None,
                    comparables=[],comparables_count=0,confidence='unavailable',analysis_reason=trade_error) for u in item['units']]
            elif any(x in item['collection_issues'] for x in ('some_comparison_locations_unverified','district_coverage_sampled')):
                for u in item['units']:
                    if u['confidence']!='unavailable':
                        u['confidence']='low'
                        if 'district_coverage_sampled' in item['collection_issues']:
                            u['analysis_reason']+='; 인접 행정구역 표본 조회로 전체 지역 포괄 여부 미확인'
            if location_audit is not None:
                for u in item['units']:
                    for t in u['comparables']:
                        loc=locations[t['location']+'|'+t['apartment_name']]
                        location_audit['comparables'][t['id']]=dict(location=t['location'],apartment_name=t['apartment_name'],
                            coordinates=loc['coordinates'],evidence_url=loc['evidence_url'],checked_at=now.isoformat())
            trade_count+=len(trades)
        except Exception as exc:
            trade_error=str(exc) if isinstance(exc,SourceError) else 'trade_data_invalid'
            # A successful new sale price invalidates any previous gap until fresh comparison succeeds.
            for u in item['units']:u['analysis_reason']='trade_source_failed'
    if molit.fallback_used:trade_error=trade_error or 'general_fallback_used'
    mapped=connected
    pstatus='not_configured' if not (apply_key or apply_client) else 'partial' if price_error or mapped<len(items) else 'ok'
    tstatus='not_configured' if not trade_key else 'partial' if trade_error or mapped<len(items) or not mapped or price_error else 'ok'
    for item in items:item['collection_issues']=sorted(set(item['collection_issues']))
    if diagnostics is not None:
        diagnostics.update(vworld_error=geo_error,geocoder='kakao' if isinstance(geo,Kakao) else 'vworld',molit_requested=bool(trade_cache))
    return pstatus,tstatus,price_count,trade_count,price_error or ('official_project_not_matched' if mapped<len(items) else None),trade_error

def atomic_write(path,data):
    validate(data)
    body=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if path.exists() and path.read_text(encoding='utf-8')==body:return False
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as handle:handle.write(body)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return True

def run(output,pages=3,attachments=True,client=None,now=None,enrichment_only=False):
    supplied_now=now is not None
    now=now or datetime.now(KST);client=client or Client()
    previous=load(output) if output.exists() else None
    if previous:validate(previous)
    previous_sources={s['id']:s for s in (previous or {}).get('sources',[])}
    sources=[]; items=[]
    try:
        if enrichment_only:raise SourceError('notice_refresh_separate_stage')
        items,partial,errors=collect(client,now,pages,attachments)
        unresolved={x['name'] for x in items if not x['apply_start_at'] or not x['eligibility']['evidence_text']}
        if unresolved:
            try:
                originals,backfill_partial,backfill_errors=collect(client,now,3,attachments,start_page=pages,target_names=unresolved)
                items.extend(originals);partial=partial or backfill_partial;errors.extend(backfill_errors)
            except Exception:
                partial=True
                for item in items:
                    if item['name'] in unresolved:item['collection_issues'].append('original_notice_backfill_failed')
        sources.append(source('gg','경기도 장애인 특별공급',BOARD,now,'partial' if partial else 'ok',previous_sources.get('gg'),len(items),'notice_or_attachment_failed' if partial else None))
    except Exception as exc:
        code=str(exc) if isinstance(exc,SourceError) else 'board_parse_error'
        sources.append(source('gg','경기도 장애인 특별공급',BOARD,now,'error',previous_sources.get('gg'),None,code))
    merged=merge((previous or {}).get('listings',[]),items,now)
    config=load(ROOT/'config/projects.json');policy=load(ROOT/'config/analysis.json')
    location_path=output.with_name('locations.json')
    location_audit=load(location_path) if location_path.exists() else dict(schema_version='1.0.0',targets={},comparables={})
    location_audit['generated_at']=now.isoformat()
    diagnostics={}
    ps,ts,pc,tc,pe,te=enrich(merged,client,now,config,policy,os.getenv('APPLYHOME_SERVICE_KEY'),os.getenv('MOLIT_SERVICE_KEY'),location_audit=location_audit,diagnostics=diagnostics)
    sources.extend([source('applyhome','청약홈 분양정보',APPLY_SOURCE,now,ps,previous_sources.get('applyhome'),pc,pe or ('missing_applyhome_key' if ps=='not_configured' else None)),
        source('molit','국토교통부 실거래가',TRADE_SOURCE,now,ts,previous_sources.get('molit'),tc,te or ('missing_molit_key' if ts=='not_configured' else None))])
    from scripts.geocoding import SOURCE as GEO_SOURCE
    if diagnostics.get('geocoder')=='kakao':
        from scripts.kakao import SOURCE as GEO_SOURCE
    geoid=diagnostics.get('geocoder','vworld')
    geostatus='not_configured' if not (os.getenv('KAKAO_REST_API_KEY') or os.getenv('VWORLD_API_KEY')) else 'partial'
    sources.append(source(geoid,'카카오 주소 좌표' if geoid=='kakao' else '브이월드 공식 좌표',GEO_SOURCE,now,geostatus,previous_sources.get(geoid),len(location_audit['targets']),
        'missing_geocoder_key' if geostatus=='not_configured' else diagnostics.get('vworld_error') or 'coordinates_not_fully_verified'))
    if enrichment_only and previous_sources.get('gg'):
        sources[0]=deepcopy(previous_sources['gg'])
    success=all(s['status']=='ok' for s in sources)
    last=now.isoformat() if success else (previous or {}).get('last_success_at')
    if success:status='ok'
    elif sources[0]['status']=='error':status='stale' if merged else 'error'
    else:status='partial'
    generated=now if supplied_now else datetime.now(KST)
    data=dict(schema_version='1.0.0',generated_at=generated.isoformat(),last_success_at=last,data_status=status,sources=sources,listings=merged)
    # Top-level partial distinguishes working notice feed with unavailable enrichment.
    if location_audit['targets']:
        from scripts.location_evidence import write_locations
        validate(data)
        current_ids={item['id'] for item in merged}
        used_trades={t['id'] for item in merged for unit in item['units'] for t in unit['comparables']}
        location_audit['targets']={k:v for k,v in location_audit['targets'].items() if k in current_ids}
        location_audit['comparables']={k:v for k,v in location_audit['comparables'].items() if k in used_trades}
        location_audit['generated_at']=data['generated_at']
        write_locations(output.with_name('locations.json'),location_audit)
    atomic_write(output,data)
    health=dict(data_status=status,listings=len(merged),sources={s['id']:s['status'] for s in sources},
        listings_with_units=sum(bool(x['units']) for x in merged),
        listings_with_prices=sum(any(u['sale_price_krw'] for u in x['units']) for x in merged),
        listings_with_gaps=sum(any(u['estimated_gap_krw'] is not None for u in x['units']) for x in merged),
        application_dates_unknown=sum(not x['apply_start_at'] or not x['apply_end_at'] for x in merged),
        eligibility_unknown=sum(x['eligibility']['yongin_status']=='unknown' for x in merged))
    print(json.dumps(health))
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as handle:
            handle.write('\n### Official data completeness\n\nWorkflow success does not mean full data coverage.\n\n')
            handle.write('| Metric | Value |\n|---|---|\n')
            for key,value in health.items():handle.write(f'| {key} | {value} |\n')
    return 1 if sources[0]['status']=='error' else 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'docs/data/latest.json')
    parser.add_argument('--pages',type=int,default=3)
    parser.add_argument('--skip-attachments',action='store_true')
    parser.add_argument('--enrichment-only',action='store_true')
    args=parser.parse_args()
    if not 1<=args.pages<=20:parser.error('pages must be 1..20')
    if args.skip_attachments:parser.error('Attachments are required for publishable eligibility validation')
    raise SystemExit(run(args.output,args.pages,True,enrichment_only=args.enrichment_only))
