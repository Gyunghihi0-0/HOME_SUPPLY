import json,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.http_client import Client,SourceError
from scripts.notice_documents import read_cached

def test_public_attachment_is_revalidated_and_changed_bytes_replace_cache(tmp_path):
    client=Client(tmp_path,pause=0)
    calls=[]
    class Response:
        def __init__(self,status,body=b'',etag='v1'):
            self.status_code=status;self.body=body;self.headers={'ETag':etag}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*args):yield self.body
    responses=iter([Response(200,b'old'),Response(304),Response(200,b'changed','v2')])
    def request(*args,**kwargs):calls.append(kwargs);return next(responses)
    client.session.request=request
    url='https://www.gg.go.kr/public.pdf'
    assert client.request(url,public_document=True)==b'old'
    assert client.request(url,public_document=True)==b'old'
    assert calls[1]['headers']['If-None-Match']=='v1'
    assert client.request(url,public_document=True)==b'changed'

def test_parsed_cache_reuses_only_identical_content_and_parser_timeout_is_bounded(tmp_path,monkeypatch):
    calls=[]
    def parse(*args,**kwargs):
        calls.append(kwargs['input'])
        if kwargs['input']==b'slow':raise subprocess.TimeoutExpired('parser',1)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'text':kwargs['input'].decode(),'tables':[]}).encode())
    monkeypatch.setattr(subprocess,'run',parse)
    assert read_cached(b'first','a.pdf',tmp_path)['text']=='first'
    assert read_cached(b'first','a.pdf',tmp_path)['text']=='first'
    assert read_cached(b'changed','a.pdf',tmp_path)['text']=='changed'
    assert calls==[b'first',b'changed']
    with pytest.raises(SourceError,match='document_parse_timeout'):read_cached(b'slow','a.pdf',tmp_path)

def test_streaming_response_cannot_run_past_collection_deadline(tmp_path,monkeypatch):
    import scripts.http_client as http
    client=Client(tmp_path,pause=0);client.deadline=10
    ticks=iter([1,11])
    monkeypatch.setattr(http.time,'monotonic',lambda:next(ticks))
    class Response:
        status_code=200;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*args):yield b'slow bytes'
    client.session.request=lambda *a,**k:Response()
    with pytest.raises(SourceError,match='notice_budget_exhausted'):client.request('https://www.gg.go.kr/test')

def test_new_notice_checkpoint_precedes_attachment_parse_without_board_download(tmp_path,monkeypatch):
    from copy import deepcopy
    from scripts import collector,notice_documents
    from tests.backend.test_pipeline import notice,NOW
    old=notice();old['status']='closed'
    rows=[{'B_IDX':1,'SUBJECT':'기존 특별공급','WRITE_DATE2':'2026-10-01'},
          {'B_IDX':9,'SUBJECT':'신규 특별공급','WRITE_DATE2':'2026-10-18'}]
    events=[]
    class PublicClient:
        cache_dir=tmp_path
        def check_robots(self,url):events.append('robots')
        def request(self,url,**kwargs):
            assert url!=collector.BOARD
            if 'getList' in url:return json.dumps({'items':rows,'total':2})
            return b'public document'
    def parsed(body,row,now):
        item=deepcopy(old);item['id']='gg_'+str(row['B_IDX'])
        item['attachments']=[{'url':'https://www.gg.go.kr/notice.pdf','name':'notice.pdf','parse_status':'pending'}]
        return item
    def document(*args):
        assert 'saved_gg_9' in events
        events.append('parsed')
        return {'text':'공식 첨부문서 텍스트 확인 자료','tables':[]}
    monkeypatch.setattr(collector,'parse_notice',parsed)
    monkeypatch.setattr(notice_documents,'read_cached',document)
    result,partial,errors=collector.collect(PublicClient(),NOW,pages=1,previous=[old],
        on_record=lambda item:events.append('saved_'+item['id']))
    assert events.index('saved_gg_9')<events.index('parsed')<events.index('saved_gg_1')
    assert len(result)==2 and not partial and not errors
