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
    previous=next((s for s in data['sources'] if s['id']=='gg'),{})
    progress_path=path.parent/'notice-progress.json'
    progress=load(progress_path) if progress_path.exists() else {'next_page':0,'attempted_at':{}}
    from scripts.diagnostic_io import write_report
    deferred=int(progress.get('next_page',0))
    order=list(dict.fromkeys([0]+([deferred] if deferred in (1,2) else [])+[1,2]))
    checkpointed={}
    def checkpoint(item):
        checkpointed[item['id']]=item
        data['listings']=merge(data['listings'],[item],now)
        entry=source('gg','경기도 장애인 특별공급',BOARD,now,'partial',previous,len(checkpointed),'notice_update_in_progress')
        data['sources']=[entry]+[s for s in data['sources'] if s['id']!='gg']
        data.update(generated_at=now.isoformat(),data_status='partial')
        atomic_write(path,data)
        progress['attempted_at'][item['id']]=now.isoformat()
        write_report(progress_path,progress)
        print('notice_checkpoint '+item['id'],flush=True)
    try:
        items,partial,errors=collect(Client(pause=.1,timeout=(5,10),retries=0),now,3,True,
                                     previous=data['listings'],on_record=checkpoint,budget_seconds=80,
                                     page_order=order,attempted_at=progress['attempted_at'])
    except Exception as exc:
        from scripts.http_client import SourceError
        code=str(exc) if isinstance(exc,SourceError) else 'notice_parse_error'
        entry=source('gg','경기도 장애인 특별공급',BOARD,now,'error',previous,len(checkpointed),code)
        data['sources']=[entry]+[s for s in data['sources'] if s['id']!='gg']
        data.update(generated_at=now.isoformat(),data_status='stale')
        atomic_write(path,data)
        raise
    data['listings']=merge(data['listings'],items,now)
    pending=[int(e.rsplit('_',1)[1]) for e in errors if e.startswith('notice_budget_exhausted_page_')]
    progress['next_page']=pending[0] if pending else 0
    write_report(progress_path,progress)
    entry=source('gg','경기도 장애인 특별공급',BOARD,now,'partial' if partial else 'ok',previous,len(items),
                 'notice_budget_exhausted' if 'notice_budget_exhausted' in errors else 'notice_or_attachment_failed' if partial else None)
    data['sources']=[entry]+[s for s in data['sources'] if s['id']!='gg']
    data.update(generated_at=now.isoformat(),data_status='partial')
    atomic_write(path,data)
    print('notice_stage_saved records='+str(len(items)),flush=True)

if __name__=='__main__':refresh(Path(sys.argv[1]))
