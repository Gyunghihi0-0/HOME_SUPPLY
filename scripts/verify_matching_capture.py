"""Replay public capture without network or credentials; output is never live data."""
import json
import os
from datetime import datetime
from scripts.pipeline import enrich, ROOT
from scripts.replay_catalog import CapturedApplyhome
from scripts.http_client import SourceError
from scripts.collector import KST
from scripts.validate import validate

class Offline:
    def request(self,*args,**kwargs):raise SourceError('offline_replay_no_network')

def main():
    for key in ('KAKAO_REST_API_KEY','VWORLD_API_KEY','MOLIT_GENERAL_SERVICE_KEY'):
        os.environ.pop(key,None)
    data=json.loads((ROOT/'docs/data/latest.json').read_text(encoding='utf-8'))
    capture=json.loads((ROOT/'tests/backend/fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))
    policy=json.loads((ROOT/'config/analysis.json').read_text(encoding='utf-8'))
    # Compare the existing captured output against its replay with grouped matching.
    def summary(rows):
        return {'priced_projects':sum(any(u['sale_price_krw'] for u in x['units']) for x in rows),
                'priced_units':sum(bool(u['sale_price_krw']) for x in rows for u in x['units']),
                'calculated_units':sum(u['estimated_gap_krw'] is not None for x in rows for u in x['units'])}
    before=summary(data['listings'])
    enrich(data['listings'],Offline(),datetime.fromisoformat(capture['observed_at'].replace('Z','+00:00')).astimezone(KST),
           {'projects':{},'trade_locations':{}},policy,None,None,apply_client=CapturedApplyhome(capture))
    validate(data)
    added=[{'name':x['name'],'units':[{'type':u['type_id'],'price':u['sale_price_krw'],
            'allocation':u['allocation_count']} for u in x['units']]} for x in data['listings'] if '_p' in x['id']]
    report={'mode':'offline_public_capture_not_live_refresh','before':before,'after':summary(data['listings']),
            'added_projects':added,'source':capture['verification_run']}
    (ROOT/'handoff/matching-improvement-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
