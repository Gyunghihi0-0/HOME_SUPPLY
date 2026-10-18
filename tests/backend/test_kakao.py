import json
import pytest
from scripts.kakao import Kakao
from scripts.http_client import SourceError

def document(parcel='212-3'):
    return dict(x='127.32',y='37.54',address=dict(address_name='경기 양평군 양서면 용담리 '+parcel,
        b_code='4183033021',region_1depth_name='경기',region_2depth_name='양평군'))

def test_exact_parcel_and_header_only_authentication():
    class Client:
        def request(self,url,**kw):
            assert kw['headers']=={'Authorization':'KakaoAK test-key'}
            assert 'key' not in kw['params'] and kw['ttl']==0
            return json.dumps({'documents':[document()]})
    geo=Kakao(Client(),'test-key')
    result=geo.locate('경기도 양평군 양서면 용담리 212-3번지 일원')
    assert result['lawd_codes']==['41830']
    assert result['coordinates']==[37.54,127.32]
    with pytest.raises(SourceError,match='exact_address_not_found'):
        geo.locate('경기도 양평군 양서면 용담리 212-4')

def test_ambiguous_result_and_block_not_promoted_to_verified_location():
    class Client:
        def request(self,*a,**kw):return json.dumps({'documents':[document(),document()]})
    with pytest.raises(SourceError,match='not_unique'):
        Kakao(Client(),'test-key').locate('경기도 양평군 양서면 용담리 212-3')
    with pytest.raises(SourceError,match='exact_address_not_found'):
        Kakao(Client(),'test-key').locate('경기도 광명시 구름산지구 A6블록')

def test_district_sampling_is_never_called_complete():
    class Client:
        def request(self,*a,**kw):return json.dumps({'documents':[
            dict(region_type='B',code='4183033021',region_1depth_name='경기',region_2depth_name='양평군')]})
    geo=Kakao(Client(),'test-key')
    assert geo.districts([37.54,127.32],2000)=={'41830':'경기 양평군'}
    assert geo.coverage_complete is False
