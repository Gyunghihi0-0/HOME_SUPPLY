from copy import deepcopy
import json
import pytest
from scripts import refresh_notices
from scripts.collector import collect,parse_notice
from scripts.http_client import SourceError
from tests.backend.test_pipeline import NOW,notice

def test_completed_notice_is_saved_before_later_source_failure(tmp_path,monkeypatch):
    from scripts.pipeline import atomic_write
    data=dict(schema_version='1.0.0',generated_at=NOW.isoformat(),last_success_at=NOW.isoformat(),data_status='ok',sources=[],listings=[notice()])
    output=tmp_path/'latest.json';atomic_write(output,data)
    newer=deepcopy(notice());newer['id']='gg_999';newer['name']='새 공고'
    newer['notice_url']='https://www.gg.go.kr/bbs/boardView.do?bIdx=999'
    newer['notice_history'][0]['notice_url']=newer['notice_url']
    def interrupted(*args,**kwargs):
        kwargs['on_record'](newer)
        saved=json.loads(output.read_text(encoding='utf-8'))
        assert {r['id'] for r in saved['listings']}=={'gg_1','gg_999'}
        raise SourceError('http_503')
    monkeypatch.setattr(refresh_notices,'collect',interrupted)
    with pytest.raises(SourceError):refresh_notices.refresh(output)
    saved=json.loads(output.read_text(encoding='utf-8'))
    assert len(saved['listings'])==2
    assert saved['last_success_at']==data['last_success_at']
    assert saved['sources'][0]['error_code']=='http_503'

def test_budget_exhaustion_is_reported_without_starting_list_request():
    class Client:
        def request(self,url,**kwargs):
            assert 'ajax' not in url
            return b''
    items,partial,errors=collect(Client(),NOW,budget_seconds=0)
    assert items==[] and partial and 'notice_budget_exhausted' in errors


def test_next_run_prioritizes_deferred_page_and_preserves_attempt_history(tmp_path,monkeypatch):
    from scripts.pipeline import atomic_write
    output=tmp_path/'latest.json'
    atomic_write(output,dict(schema_version='1.0.0',generated_at=NOW.isoformat(),last_success_at=None,
                            data_status='partial',sources=[],listings=[notice()]))
    progress=tmp_path/'notice-progress.json'
    progress.write_text(json.dumps({'next_page':2,'attempted_at':{'gg_1':NOW.isoformat()}}),encoding='utf-8')
    def resumed(*args,**kwargs):
        assert kwargs['page_order']==[0,2,1]
        assert kwargs['attempted_at']['gg_1']==NOW.isoformat()
        return [],True,['notice_budget_exhausted','notice_budget_exhausted_page_1']
    monkeypatch.setattr(refresh_notices,'collect',resumed)
    refresh_notices.refresh(output)
    saved=json.loads(progress.read_text(encoding='utf-8'))
    assert saved['next_page']==1 and saved['attempted_at']['gg_1']==NOW.isoformat()
    assert len(json.loads(output.read_text(encoding='utf-8'))['listings'])==1
