import json,os,time
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from scripts.collection_health import attach_health,record_success,record_failure
from scripts.http_client import Client,SourceError
from scripts.apis import Applyhome
from scripts.kakao import Kakao

def client_with_response(tmp_path,body):
    client=Client(tmp_path,pause=0);calls=[]
    class Response:
        status_code=200;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*args):yield json.dumps(body).encode()
    client.session.request=lambda *a,**k:(calls.append(1) or Response())
    return client,calls

def test_valid_empty_response_is_collection_success_even_without_matching_projects(tmp_path):
    client,calls=client_with_response(tmp_path,{'data':[],'totalCount':0,'matchCount':0})
    assert Applyhome(client,'test-key').get('getAPTLttotPblancDetail',{})==[]
    entry=attach_health({'id':'applyhome','status':'partial'},client)
    assert entry['collection_status']=='ok' and entry['last_collected_at']
    assert entry['status']=='partial' and entry['collection_responses']==1

def test_cached_response_keeps_original_collection_time_not_now(tmp_path):
    client,calls=client_with_response(tmp_path,{'data':[],'totalCount':0})
    api=Applyhome(client,'test-key');api.get('getAPTLttotPblancDetail',{})
    stamp=time.time()-3600
    for path in tmp_path.glob('*.bin'):os.utime(path,(stamp,stamp))
    client.collection_audit.clear()
    api.get('getAPTLttotPblancDetail',{})
    entry=attach_health({'id':'applyhome','status':'partial'},client)
    assert len(calls)==1 and entry['collection_status']=='cached'
    assert abs(datetime.fromisoformat(entry['last_collected_at']).timestamp()-stamp)<1

def test_http_200_authentication_error_is_not_collection_success(tmp_path):
    client,calls=client_with_response(tmp_path,{'code':30,'message':'invalid test key'})
    with pytest.raises(SourceError):Applyhome(client,'test-key').get('getAPTLttotPblancDetail',{})
    entry=attach_health({'id':'applyhome','status':'partial'},client,{'last_collected_at':'2026-10-18T10:00:00+09:00'})
    assert entry['collection_status']=='error' and entry['collection_responses']==0
    assert entry['last_collected_at']=='2026-10-18T10:00:00+09:00'

def test_partial_response_failures_are_not_hidden_and_timestamp_compares_timezones():
    client=SimpleNamespace(collection_audit={},response_meta=SimpleNamespace(observed_at='2026-11-08T08:00:00+00:00',cached=False))
    record_success(client,'molit');record_failure(client,'molit')
    entry=attach_health({'id':'molit','status':'partial'},client,{'last_collected_at':'2026-11-08T16:00:00+09:00'})
    assert entry['collection_status']=='partial' and entry['collection_errors']==1
    assert entry['last_collected_at']=='2026-11-08T08:00:00+00:00'

def test_no_current_response_does_not_infer_success_from_large_saved_record_count():
    entry=attach_health({'id':'molit','status':'partial','records_count':75000},object())
    assert entry['collection_status']=='not_checked' and entry['last_collected_at'] is None

def test_empty_kakao_search_is_valid_collection_but_not_a_verified_location(tmp_path):
    client,calls=client_with_response(tmp_path,{'documents':[]})
    with pytest.raises(SourceError,match='exact_address_not_found'):
        Kakao(client,'test-key').locate('경기도 광명시 소하동 1')
    entry=attach_health({'id':'kakao','status':'partial'},client)
    assert entry['collection_status']=='ok' and entry['collection_errors']==0

def test_valid_empty_notice_list_records_real_collection_success(tmp_path):
    from scripts.collector import collect
    from tests.backend.test_pipeline import NOW
    client,calls=client_with_response(tmp_path,{'items':[],'total':0})
    client.check_robots=lambda url:None
    items,partial,errors=collect(client,NOW,pages=1)
    assert items==[] and not partial and not errors
    assert attach_health({'id':'gg','status':'ok'},client)['collection_status']=='ok'

def test_new_health_fields_validate_without_changing_legacy_schema_version():
    from scripts.pipeline import ROOT
    from scripts.validate import validate
    data=json.loads((ROOT/'contracts/example-latest.json').read_text(encoding='utf-8'))
    client=SimpleNamespace(collection_audit={},response_meta=SimpleNamespace(observed_at='2026-11-08T08:00:00Z',cached=False))
    record_success(client,data['sources'][0]['id'])
    attach_health(data['sources'][0],client)
    validate(data)
    assert data['schema_version']=='1.0.0'
