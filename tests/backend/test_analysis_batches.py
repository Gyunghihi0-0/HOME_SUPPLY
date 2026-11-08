from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from scripts import pipeline,daily_refresh
from scripts.http_client import SourceError
from tests.backend.test_pipeline import notice,NOW

def test_budget_stops_safely_and_rolls_back_unfinished_item(monkeypatch):
    clock=[0];calls=[];saved=[]
    monkeypatch.setattr(pipeline.time,'monotonic',lambda:clock[0])
    first=notice();first.update(id='first',status='open')
    second=deepcopy(first);second.update(id='second',status='closed')
    original=deepcopy(second)
    class Catalog:
        def discover(self,item):
            calls.append(item['id']);clock[0]=5 if item['id']=='first' else 11
            raise SourceError('official_project_not_in_catalog')
    diagnostics={}
    pipeline.enrich([second,first],object(),NOW,{'projects':{},'trade_locations':{}},{},None,None,
        apply_client=Catalog(),diagnostics=diagnostics,deadline=10,
        on_record=lambda item,done:saved.append((deepcopy(item),done)))
    assert calls==['first','second']
    assert saved[0][1] and not saved[1][1]
    assert diagnostics['analysis_deferred'] and diagnostics['analysis_processed']==1
    assert second['units']==original['units']
    assert second['collection_issues']==sorted(set(original['collection_issues']+['analysis_deferred']))

def test_checkpoint_survives_later_unhandled_failure(tmp_path,monkeypatch):
    data=json.loads((pipeline.ROOT/'contracts/example-latest.json').read_text(encoding='utf-8'))
    output=tmp_path/'latest.json';output.write_text(json.dumps(data),encoding='utf-8')
    def interrupted(items,*args,**kwargs):
        items[0]['name']='체크포인트 저장 확인'
        kwargs['on_record'](items[0],True)
        raise RuntimeError('later worker failed')
    monkeypatch.setattr(pipeline,'enrich',interrupted)
    with pytest.raises(RuntimeError):pipeline.run(output,now=NOW,enrichment_only=True)
    saved=json.loads(output.read_text(encoding='utf-8'))
    assert saved['listings'][0]['name']=='체크포인트 저장 확인'
    assert saved['last_success_at']==data['last_success_at']
    assert saved['data_status']=='partial'
    assert (tmp_path/'analysis-progress.json').exists()

@pytest.mark.parametrize('outage',[False,True])
def test_planned_batch_is_warning_but_actual_source_outage_still_fails(tmp_path,monkeypatch,outage):
    data=json.loads((pipeline.ROOT/'contracts/example-latest.json').read_text(encoding='utf-8'))
    data['data_status']='partial'
    for source in data['sources']:
        source.update(status='partial',error_code='analysis_batch_deferred',message='분할 처리')
    if outage:data['sources'][-1].update(status='error',error_code='network_error')
    output=tmp_path/'latest.json';output.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(daily_refresh.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    assert daily_refresh.refresh(output)==(1 if outage else 0)

def test_budget_does_not_hide_authentication_error(monkeypatch):
    clock=[0]
    monkeypatch.setattr(pipeline.time,'monotonic',lambda:clock[0])
    class Catalog:
        def discover(self,item):
            clock[0]=11
            raise SourceError('http_401')
    diagnostics={}
    pipeline.enrich([notice()],object(),NOW,{'projects':{},'trade_locations':{}},{},None,None,
        apply_client=Catalog(),diagnostics=diagnostics,deadline=10)
    assert diagnostics['analysis_deferred']
    assert diagnostics['source_failures']=={'applyhome':'http_401'}
