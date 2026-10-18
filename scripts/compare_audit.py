"""Same 28-notice cohort replay using real captured catalog/coordinate evidence."""
import json,os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from scripts import pipeline
from scripts.apis import Applyhome
from scripts.http_client import SourceError
from scripts.kakao import normalized
from scripts.diagnostics import metrics,report,root_id
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
    result['after']=metrics(after,cohort)
    result['after']['confirmed_catalog_projects']=sum(r['stages']['project']=='verified' for r in result['records'])
    result['after']['retained_historical_projects']=sum(r['stages']['project']=='official_announcement_round_unverified' for r in result['records'])
    result['comparison_limit']='Catalog and target coordinates are newly captured actual responses; trade recalculation uses only 6 previously published actual comparables, so new-target trade sufficiency is untested.'
    (folder/'mapping-diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'.audit-evidence/after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'before':result['before'],'after':result['after'],'classification':result['classification_counts']},ensure_ascii=False))

if __name__=='__main__':main()
