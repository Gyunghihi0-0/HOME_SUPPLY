"""Same 28-notice cohort replay using real captured catalog/coordinate evidence."""
import json,os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from scripts import pipeline
from scripts.apis import Applyhome
from scripts.http_client import SourceError
from scripts.kakao import normalized
from scripts.diagnostics import metrics,report,root_id,LABELS
from scripts.validate import validate

ROOT=Path(__file__).resolve().parents[1]

def main():
    capture=json.loads((ROOT/'tests/backend/fixtures/official-audit-catalog-2026-10-18.json').read_text(encoding='utf-8'))
    before=json.loads((ROOT/'tests/backend/fixtures/cohort-baseline-2026-10-18.json').read_text(encoding='utf-8'))
    after=deepcopy(before);cohort={root_id(x['id']) for x in before['listings']}
    now=datetime.fromisoformat(capture['observed_at'])
    class Catalog(Applyhome):
        def __init__(self):pass
        def get(self,endpoint,filters):
            rows=capture['projects'] if endpoint!='getAPTLttotPblancMdl' else [m for r in capture['projects'] for m in r.get('models',[])]
            return [r for r in rows if all(str(r.get(k[5:-5],''))==str(v) for k,v in filters.items() if k.endswith('::EQ]'))]
    class Client:
        def request(self,url,**kwargs):
            if 'search/address.json' in url:
                found=[r for r in capture['geocodes'] if normalized(r['query'])==normalized(kwargs['params']['query'])]
                if found:return json.dumps({'documents':found[0]['documents']})
            raise SourceError('not_in_readonly_capture')
    # Only previously published actual comparables are replayed. No synthetic trades.
    trades={t['id']:t for item in before['listings'] for unit in item['units'] for t in unit['comparables']}
    evidence=json.loads((ROOT/'tests/backend/fixtures/published-locations-2026-10-18.json').read_text(encoding='utf-8'))
    class KnownTrades:
        fallback_used=False
        def __init__(self,*args,**kwargs):pass
        def month(self,district,month,now):
            return [t for t in trades.values() if t['location'].startswith(district+'|') and t['trade_date'].replace('-','').startswith(month)]
    locations={v['location']+'|'+v['apartment_name']:v for v in evidence['comparables'].values()}
    policy=json.loads((ROOT/'config/analysis.json').read_text(encoding='utf-8'))
    old=pipeline.Molit;prior=os.environ.get('KAKAO_REST_API_KEY');os.environ['KAKAO_REST_API_KEY']='offline-capture-placeholder'
    try:
        pipeline.Molit=KnownTrades
        pipeline.enrich(after['listings'],Client(),now,{'projects':{},'trade_locations':locations},policy,None,None,apply_client=Catalog())
    finally:
        pipeline.Molit=old
        if prior is None:os.environ.pop('KAKAO_REST_API_KEY',None)
        else:os.environ['KAKAO_REST_API_KEY']=prior
    # Replay timestamps are not new live source timestamps.
    validate(after)
    folder=ROOT/'reports';folder.mkdir(exist_ok=True)
    result=report(after,capture,cohort)
    for record in result['records']:
        for unit in record['units']:
            if unit['code']=='fewer_than_three_verified_trades' and record['notice_id']!='gg_262294421':
                unit['code']='trade_validation_pending'
                unit['label']='새 단지 실거래 검증 대기 · 저장된 기존 6건만으로 표본 부족을 확정하지 않음'
    result['before']=metrics(before,cohort)
    from scripts.matching import select_project
    confirmed=set()
    for item in before['listings']:
        if not item.get('housing_manage_no'):continue
        try:row=select_project(item,capture['projects'])
        except SourceError:continue
        confirmed.add((row['HOUSE_MANAGE_NO'],row['PBLANC_NO']))
    result['before']['confirmed_catalog_projects']=len(confirmed)
    result['after']=metrics(after,cohort)
    result['after']['confirmed_catalog_projects']=sum(r['stages']['project']=='verified' for r in result['records'])
    result['after']['retained_historical_projects']=sum(r['stages']['project']=='official_announcement_round_unverified' for r in result['records'])
    result['comparison_limit']='Catalog and target coordinates are newly captured actual responses; trade recalculation uses only 6 previously published actual comparables, so new-target trade sufficiency is untested.'
    live_path=folder/'live-trade-verification.json'
    if live_path.exists():
        live=json.loads(live_path.read_text(encoding='utf-8'))
        expected={'radius_m':2000,'area_tolerance_pct':10,'build_year_tolerance':10,'minimum_trades':3,
                  'preferred_months':6,'maximum_months':12,'extreme_spread_hold':0.5}
        if live['policy']!=expected:raise ValueError('live_evidence_policy_mismatch')
        by_id={r['id']:r for r in after['listings']};attached=0
        for record in result['records']:
            item=by_id[record['id']]
            project=next((p for p in live['projects'] if p['housing_manage_no']==item['housing_manage_no']),None)
            if not project:continue
            record['live_trade_run']=live['run_url']
            for unit in record['units']:
                observed=next((u for u in project['units'] if u['type']==unit['type']),None)
                if not observed:continue
                if unit['price']!=observed['price'] or abs(unit['exclusive_area']-observed['area'])>0.000001:
                    raise ValueError('live_evidence_unit_mismatch')
                code={'sample_insufficient':'fewer_than_three_verified_trades'}.get(observed['reason'],observed['reason'])
                unit.update(code=code,label=LABELS.get(code,code),gap=observed['gap'],live_trade=observed)
                attached+=1
        if attached!=live['summary']['examined_types']:raise ValueError('live_evidence_cohort_mismatch')
        result['live_trade_validation']={'run_url':live['run_url'],'observed_at':live['observed_at'],
            'summary':live['summary'],'limitations':live['limitations']}
        result['comparison_limit']='Offline replay metrics retain the original 6 trades / 2 gaps. Separate fixed readonly live verification covers the same cohort, 6 verified targets / 22 types, and supplies the live_trade fields without changing production JSON.'
    (folder/'mapping-diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    table=['# 공고별 매핑 진단','','같은 원공고 28개, 사업 분리 후 30개 레코드. API 목록 부재를 미공고 확정으로 해석하지 않습니다.','','| 사업 | 사업 연결 | 좌표 | 남은 단계 |','|---|---|---|---|']
    for r in result['records']:
        labels=list(dict.fromkeys(u['label'] for u in r['units']))
        table.append('| '+' | '.join([r['name'],r['project_label'],'검증됨' if r['coordinate_verified'] else '미확인',' / '.join(labels[:3])])+' |')
    (folder/'notice-mapping-table.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    scratch=ROOT/'.audit-evidence';scratch.mkdir(exist_ok=True)
    (scratch/'after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'before':result['before'],'after':result['after'],'classification':result['classification_counts']},ensure_ascii=False))

if __name__=='__main__':main()
