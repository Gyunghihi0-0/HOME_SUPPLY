"""Reproduce a verified public API capture; never used as live authentication evidence."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from scripts.apis import Applyhome,APPLY_SOURCE
from scripts.collector import KST
from scripts.http_client import Client,SourceError
from scripts.pipeline import enrich,load,atomic_write,ROOT

class CapturedApplyhome(Applyhome):
    def __init__(self,capture):
        self.rows=capture['projects']
        if capture['source_url']!=APPLY_SOURCE or not capture.get('verification_run','').startswith('https://github.com/Gyunghihi0-0/HOME_SUPPLY/actions/runs/'):
            raise SourceError('unverified_catalog_capture')
    def get(self,endpoint,filters):
        rows=self.rows
        if endpoint=='getAPTLttotPblancMdl':rows=[m for r in rows for m in r['models']]
        elif endpoint!='getAPTLttotPblancDetail':raise SourceError('capture_endpoint_not_supported')
        result=[]
        for row in rows:
            if all(str(row.get(k[5:-5],''))==str(v) for k,v in filters.items() if k.endswith('::EQ]')):
                # The captured data is already bounded; exact matching is performed by discover().
                result.append(row)
        return result

def replay(input_path,capture_path,output_path):
    data=load(input_path);capture=load(capture_path);now=datetime.now(KST)
    from datetime import date
    if abs((now.date()-date.fromisoformat(capture['observed_on'])).days)>1:raise SourceError('capture_too_old_for_publication')
    config=load(ROOT/'config/projects.json');policy=load(ROOT/'config/analysis.json')
    stats=enrich(data['listings'],Client(),now,config,policy,None,None,apply_client=CapturedApplyhome(capture))
    for source in data['sources']:
        if source['id']=='applyhome':
            source.update(status='partial',records_count=stats[2],error_code=stats[4],
                message='Verified official API capture: '+capture['verification_run'])
            if capture.get('observed_at'):source['checked_at']=capture['observed_at']
        elif source['id']=='molit':
            source.update(status='partial',records_count=0,error_code='comparison_not_run_missing_coordinates',message='Price capture replay; live comparison was not run')
    if not any(s['id']=='vworld' for s in data['sources']):
        from scripts.pipeline import source
        from scripts.geocoding import SOURCE
        data['sources'].append(source('vworld','브이월드 공식 좌표',SOURCE,now,'not_checked',count=0,code='live_geocoding_not_run'))
    data['data_status']='partial';data['generated_at']=now.isoformat()
    # Only use the capture's original check time; replay is not a new live source check.
    atomic_write(output_path,data)
    print(json.dumps(dict(priced_listings=stats[2],catalog_projects=len(capture['projects']),data_status='partial')))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();replay(args.input,args.capture,args.output)
