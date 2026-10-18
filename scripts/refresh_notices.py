"""Isolated notice stage: an outage cannot consume the price-analysis budget."""
import sys
from pathlib import Path
from datetime import datetime
from scripts.collector import collect, KST, BOARD
from scripts.http_client import Client
from scripts.pipeline import load, merge, atomic_write, source

def refresh(path):
    now=datetime.now(KST)
    data=load(path)
    print('notice_stage_start',flush=True)
    items,partial,errors=collect(Client(),now,3,True)
    data['listings']=merge(data['listings'],items,now)
    previous=next((s for s in data['sources'] if s['id']=='gg'),{})
    entry=source('gg','경기도 장애인 특별공급',BOARD,now,'partial' if partial else 'ok',previous,len(items),'notice_or_attachment_failed' if partial else None)
    data['sources']=[entry]+[s for s in data['sources'] if s['id']!='gg']
    data.update(generated_at=now.isoformat(),data_status='partial')
    atomic_write(path,data)
    print('notice_stage_saved records='+str(len(items)),flush=True)

if __name__=='__main__':refresh(Path(sys.argv[1]))
