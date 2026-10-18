from copy import deepcopy
from pathlib import Path
import json
import pytest
from scripts.matching import select_project,canonical_name
from scripts.http_client import SourceError
from scripts.provider_diagnostics import classify_provider_error
from scripts.block_locations import resolve_block_location

ROOT=Path(__file__).resolve().parents[2]

def capture():return json.loads((ROOT/'tests/backend/fixtures/official-audit-catalog-2026-10-18.json').read_text(encoding='utf-8'))

def test_actual_brand_and_block_matches_without_neighbor_mixup():
    rows=capture()['projects']
    assert select_project({'name':'산곡역자이힐스테이트&하늘채','address':'인천광역시 부평구 산곡동 10 번지 일원'},rows)['HOUSE_NM']=='산곡역자이힐스테이트앤하늘채'
    assert select_project({'name':'인천계양 A6블록 공공분양주택 장애인 특별공급 안내','address':'인천계양 A6 블록'},rows)['HOUSE_NM']=='인천계양지구 A6블록 공공분양주택(본청약)'
    with pytest.raises(SourceError):select_project({'name':'경기광주역 롯데캐슬 시그니처 2단지','address':'경기도 광주시 쌍령동 산54-29번지'},rows)
    with pytest.raises(SourceError):select_project({'name':'고덕 우미 린 더 프리미어','address':'경기도 평택시 고덕동 일원(고덕 국제화계획지구 내 Abc-33블록)'},rows)

def test_failure_classes_are_distinct():
    row={'HOUSE_NM':'공식 테스트','HSSPLY_ADRES':'경기도 평택시 테스트지구 A1BL','HOUSE_MANAGE_NO':'1','PBLANC_NO':'2'}
    with pytest.raises(SourceError,match='block_mismatch'):
        select_project({'name':'공식 테스트','address':'경기도 평택시 테스트지구 A2BL'},[row])
    with pytest.raises(SourceError,match='address_mismatch'):
        select_project({'name':'공식 테스트','address':'주소 미확인'},[row])
    with pytest.raises(SourceError,match='name_mismatch'):
        select_project({'name':'다른 이름','address':row['HSSPLY_ADRES']},[row])
    with pytest.raises(SourceError,match='multiple_candidates'):
        select_project({'name':'공식 테스트','address':row['HSSPLY_ADRES']},[row,dict(row,PBLANC_NO='3')])
    with pytest.raises(SourceError,match='not_in_catalog'):
        select_project({'name':'신규 사업','address':'알 수 없음'},[row])


def test_same_block_name_cannot_override_different_city():
    row={'HOUSE_NM':'공식 테스트','HSSPLY_ADRES':'경기도 평택시 테스트지구 A1BL','HOUSE_MANAGE_NO':'1','PBLANC_NO':'2'}
    with pytest.raises(SourceError,match='address_mismatch'):
        select_project({'name':'공식 테스트','address':'경기도 광명시 테스트지구 A1BL'},[row])

@pytest.mark.parametrize('code,stage',[('vworld_api_INCORRECT_KEY','authentication_configuration'),
    ('vworld_api_PARAM_REQUIRED','request_format'),('vworld_http_502','upstream_http_failure'),
    ('vworld_RemoteDisconnected','transport_failure')])
def test_provider_error_does_not_guess_auth_from_transport(code,stage):
    assert classify_provider_error(code)['stage']==stage

def test_reviewed_block_geometry_requires_project_identity_and_government_evidence():
    item={'id':'example','address':'경기도 광명시 구름산지구 A6BL','housing_manage_no':'1','pblanc_no':'2'}
    record={'reviewed':True,'evidence_url':'https://www.gm.go.kr/example','source_sha256':'a'*64,'checked_at':'2026-10-18T10:00:00+09:00',
        'housing_manage_no':'1','pblanc_no':'2','block':'A6','crs':'EPSG:4326','lawd_codes':['41210'],
        'geometry':{'type':'Polygon','coordinates':[[[126.8,37.4],[126.801,37.4],[126.801,37.401],[126.8,37.401],[126.8,37.4]]]}}
    result=resolve_block_location(item,None,{'example':record})
    assert result['coordinates']==pytest.approx([37.4005,126.8005],abs=1e-4)
    for change in [{'pblanc_no':'3'},{'evidence_url':'https://advertisement.example/map'},{'reviewed':False},{'crs':'EPSG:5179'}]:
        with pytest.raises(SourceError):resolve_block_location(item,None,{'example':dict(record,**change)})
    with pytest.raises(SourceError,match='geometry_missing'):resolve_block_location(item,None,{})

def test_actual_kakao_bracket_address_is_not_lost():
    from scripts.kakao import Kakao
    data=capture()
    row=next(r for r in data['projects'] if r['HOUSE_NM']=='아크메르 동탄 95')
    observed=next(g for g in data['geocodes'] if g['housing_manage_no']==row['HOUSE_MANAGE_NO'])
    class Client:
        def request(self,url,**kwargs):
            assert kwargs['params']['query']==observed['query']
            return json.dumps({'documents':observed['documents']})
    assert Kakao(Client(),'test-key').locate(row['HSSPLY_ADRES'])['coordinates']==pytest.approx([37.2047231856721,127.070449094191])

def test_vworld_auth_error_survives_uncached_response():
    from scripts.geocoding import VWorld
    class Client:
        def request(self,*args,**kwargs):return json.dumps({'response':{'status':'ERROR','error':{'code':'INCORRECT_KEY'}}})
    with pytest.raises(SourceError,match='vworld_api_INCORRECT_KEY'):
        VWorld(Client(),'test-key').locate('경기도 광명시 소하동 1')

def test_actual_supply_area_is_never_used_as_exclusive_area():
    from scripts.structured import official_type_area
    model=next(r for r in capture()['projects'] if r['HOUSE_NM']=='아크메르 동탄 99')['models'][0]
    assert official_type_area(model['HOUSE_TY'])==84.9916
    assert float(model['SUPLY_AR'])==124.1106
    assert official_type_area(model['SUPLY_AR'])!=84.9916
    assert official_type_area(84.9916) is None

def test_exact_area_conflict_holds_only_the_affected_unit(monkeypatch):
    from scripts.pipeline import enrich
    from scripts.apis import empty_unit
    from tests.backend.test_pipeline import notice,NOW,BrokenClient
    from scripts.replay_catalog import CapturedApplyhome
    monkeypatch.delenv('KAKAO_REST_API_KEY',raising=False);monkeypatch.delenv('VWORLD_API_KEY',raising=False)
    item=notice();item.update(name='쌍용 더 플래티넘 한강',address='경기도 양평군 양서면 용담리 212-3번지 일원')
    item['units']=[dict(empty_unit('84A',84.99),allocation_count=1),dict(empty_unit('84B'),allocation_count=1)]
    data=capture()
    class Catalog(CapturedApplyhome):
        def get(self,endpoint,filters):
            if endpoint=='getAPTLttotPblancMdl':
                rows=[m for r in self.rows for m in r.get('models',[]) ]
            else:rows=self.rows
            return [r for r in rows if all(str(r.get(k[5:-5],''))==str(v) for k,v in filters.items() if k.endswith('::EQ]'))]
    enrich([item],BrokenClient(),NOW,dict(projects={},trade_locations={}),dict(version='test',approved=True),None,None,apply_client=Catalog(data))
    assert item['units'][0]['analysis_reason']=='official_exclusive_area_conflict'
    assert item['units'][0]['sale_price_krw'] is None
    assert item['units'][1]['area_sqm']==84.8542
    assert item['units'][1]['sale_price_krw']==746000000
