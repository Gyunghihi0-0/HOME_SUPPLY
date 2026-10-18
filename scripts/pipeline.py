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

ROOT=Path(__file__).resolve().parents[1]

def load(path):return json.loads(path.read_text(encoding='utf-8'))

def source(ident,name,url,now,status='not_checked',previous=None,count=None,code=None):
    return dict(id=ident,name=name,url=url,status=status,checked_at=now.isoformat(),last_success_at=now.isoformat() if status=='ok' else (previous or {}).get('last_success_at'),
        error_code=code,message=code,records_count=count)

def merge(previous,items,now):
    result={x['id']:deepcopy(x) for x in previous}
    for new in sorted(items,key=lambda x:(x['notice_updated_at'] or '',x['id'])):
        # Exact address + exact project name only. Never merge a later supply round,
        # multi-block title, or an announcement whose address is missing.
        if new['id'] not in result and new['address'] and new['notice_history'][0]['change_type'] in ('correction','cancellation') and not any(x in new['name'] for x in ('추가','후속','재공급','재모집')):
            matches=[x for x in result.values() if x['address']==new['address'] and x['name']==new['name']
                and x['pblanc_no']==new['pblanc_no']]
            if len(matches)==1:
                new=deepcopy(new);new['id']=matches[0]['id']
        old=result.get(new['id'])
        if old:
            hashes={h['content_sha256'] for h in old['notice_history']}
            additions=[deepcopy(h) for h in new['notice_history'] if h['content_sha256'] not in hashes]
            for h in additions:
                if h['change_type']=='initial' and any(prior['notice_url']==h['notice_url'] for prior in old['notice_history']):h['change_type']='changed'
            history=old['notice_history']+additions
            if (new['notice_updated_at'] or '')<(old['notice_updated_at'] or ''):
                old['notice_history']=history
                continue
            new['notice_history']=history
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

def enrich(items,client,now,config,policy,apply_key,trade_key):
    apply=Applyhome(client,apply_key); molit=Molit(client,trade_key,os.getenv('MOLIT_ALLOW_GENERAL_FALLBACK','').lower()=='true',general_key=os.getenv('MOLIT_GENERAL_SERVICE_KEY'))
    price_error=None;trade_error=None;price_count=0;trade_count=0;trade_cache={}
    for item in items:
        mapping=config['projects'].get(item['id'])
        if not mapping:
            item['collection_issues']=sorted(set(item['collection_issues']+['official_project_mapping_required']))
            continue
        if not mapping.get('evidence_url') or not mapping.get('official_address'):
            price_error='mapping_evidence_required';continue
        try:
            detail,models=apply.project(mapping)
            units=[]
            for model in models:
                unit_mapping=mapping.get('units',{}).get(str(model['MODEL_NO']))
                # API SUPLY_AR is supply area, not exclusive area. Never use it as area_sqm.
                if not unit_mapping or unit_mapping['house_ty']!=model['HOUSE_TY'] or not unit_mapping.get('evidence_url'):continue
                unit=empty_unit(str(model['MODEL_NO']),unit_mapping.get('area_sqm'))
                unit['allocation_count']=unit_mapping.get('disability_allocation_count')
                unit['sale_price_krw']=won(model.get('LTTOT_TOP_AMOUNT'))
                if unit['sale_price_krw']:
                    unit['sale_price_basis']='maximum_base_price';unit['sale_price_evidence_url']=APPLY_SOURCE
                units.append(unit)
            if not units:raise SourceError('exclusive_area_and_disability_allocation_review_required')
            item.update(housing_manage_no=mapping['housing_manage_no'],pblanc_no=mapping['pblanc_no'],units=units,
                housing_type={'01':'private_apt','03':'public_apt'}.get(detail.get('HOUSE_DTL_SECD'),'unknown'))
            price_count+=1
        except Exception as exc:
            price_error=str(exc) if isinstance(exc,SourceError) else 'price_data_invalid'
            continue
        target=mapping.get('location')
        item['location_verified']=bool(target and target.get('coordinates') and target.get('evidence_url'))
        if not target or not target.get('lawd_codes'):
            trade_error='verified_target_location_required';continue
        try:
            trades=[]
            day=months_before(now.date(),policy['maximum_months']).replace(day=1)
            while day<=now.date():
                for lawd in target['lawd_codes']:
                    cache_key=(lawd,day.strftime('%Y%m'))
                    if cache_key not in trade_cache:trade_cache[cache_key]=molit.month(*cache_key,now)
                    trades.extend(trade_cache[cache_key])
                day=(day.replace(day=28)+timedelta(days=4)).replace(day=1)
            item['units']=[calculate(u,trades,target,config['trade_locations'],policy,now.date()) for u in item['units']]
            trade_count+=len(trades)
        except Exception as exc:
            trade_error=str(exc) if isinstance(exc,SourceError) else 'trade_data_invalid'
            # A successful new sale price invalidates any previous gap until fresh comparison succeeds.
            for u in item['units']:u['analysis_reason']='trade_source_failed'
    if molit.fallback_used:trade_error=trade_error or 'general_fallback_used'
    mapped=sum(x['id'] in config['projects'] for x in items)
    pstatus='not_configured' if not apply_key else 'partial' if price_error or mapped<len(items) else 'ok'
    tstatus='not_configured' if not trade_key else 'partial' if trade_error or mapped<len(items) or not mapped or price_error else 'ok'
    return pstatus,tstatus,price_count,trade_count,price_error or ('official_project_mapping_required' if mapped<len(items) else None),trade_error

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

def run(output,pages=3,attachments=True,client=None,now=None):
    supplied_now=now is not None
    now=now or datetime.now(KST);client=client or Client()
    previous=load(output) if output.exists() else None
    if previous:validate(previous)
    previous_sources={s['id']:s for s in (previous or {}).get('sources',[])}
    sources=[]; items=[]
    try:
        items,partial,errors=collect(client,now,pages,attachments)
        sources.append(source('gg','경기도 장애인 특별공급',BOARD,now,'partial' if partial else 'ok',previous_sources.get('gg'),len(items),'notice_or_attachment_failed' if partial else None))
    except Exception as exc:
        code=str(exc) if isinstance(exc,SourceError) else 'board_parse_error'
        sources.append(source('gg','경기도 장애인 특별공급',BOARD,now,'error',previous_sources.get('gg'),None,code))
    merged=merge((previous or {}).get('listings',[]),items,now)
    config=load(ROOT/'config/projects.json');policy=load(ROOT/'config/analysis.json')
    ps,ts,pc,tc,pe,te=enrich(merged,client,now,config,policy,os.getenv('APPLYHOME_SERVICE_KEY'),os.getenv('MOLIT_SERVICE_KEY'))
    sources.extend([source('applyhome','청약홈 분양정보',APPLY_SOURCE,now,ps,previous_sources.get('applyhome'),pc,pe or ('missing_applyhome_key' if ps=='not_configured' else None)),
        source('molit','국토교통부 실거래가',TRADE_SOURCE,now,ts,previous_sources.get('molit'),tc,te or ('missing_molit_key' if ts=='not_configured' else None))])
    success=all(s['status']=='ok' for s in sources)
    last=now.isoformat() if success else (previous or {}).get('last_success_at')
    if success:status='ok'
    elif sources[0]['status']=='error':status='stale' if merged else 'error'
    else:status='partial'
    generated=now if supplied_now else datetime.now(KST)
    data=dict(schema_version='1.0.0',generated_at=generated.isoformat(),last_success_at=last,data_status=status,sources=sources,listings=merged)
    # Top-level partial distinguishes working notice feed with unavailable enrichment.
    atomic_write(output,data)
    print(json.dumps(dict(data_status=status,listings=len(merged),sources={s['id']:s['status'] for s in sources})))
    return 1 if sources[0]['status']=='error' else 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'docs/data/latest.json')
    parser.add_argument('--pages',type=int,default=3)
    parser.add_argument('--skip-attachments',action='store_true')
    args=parser.parse_args()
    if not 1<=args.pages<=20:parser.error('pages must be 1..20')
    if args.skip_attachments:parser.error('Attachments are required for publishable eligibility validation')
    raise SystemExit(run(args.output,args.pages,True))
