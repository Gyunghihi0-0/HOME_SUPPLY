import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import pytest
from scripts.collector import parse_period,attachment_has_eligibility_restriction,KST
from scripts.eligibility import classify
from scripts.structured import allocation_units,exclusive_areas,official_type_area
from scripts.matching import same_project,select_project
from scripts.pipeline import merge,enrich
from scripts.apis import Applyhome,empty_unit
from scripts.http_client import SourceError
from scripts.geocoding import VWorld

NOW=datetime(2026,10,18,15,tzinfo=KST)

def test_real_disability_allocation_is_not_institution_total():
    rows=[['신청형','배정 세대','예비 세대'],['합계','7','35'],['84A','4','20'],['84B','1','5'],['84C','2','10']]
    units=allocation_units([rows])
    assert [(u['type_id'],u['allocation_count']) for u in units]==[('84A',4),('84B',1),('84C',2)]
    assert all(u['area_sqm'] is None for u in units)
    assert allocation_units([[['주택형','기관추천'],['84A','100']]])==[]

def test_conflicting_table_counts_are_not_silently_overwritten():
    with pytest.raises(ValueError):allocation_units([[['신청형','배정 세대'],['84A','4'],['84A','5']]])

def test_real_pdf_area_alias_row_requires_heading():
    unit=empty_unit('84A')
    line='84.7637A 84A 84.7637 26.7210 111.4847'
    assert exclusive_areas(line,[unit])[0]['area_sqm'] is None
    assert exclusive_areas('주거 전용면적\n'+line,[unit])[0]['area_sqm']==84.7637

def test_score_and_disqualification_boilerplate_do_not_limit_disability():
    assert not attachment_has_eligibility_restriction('신청자격에 대하여 확인한 결과 부적격자(공급대상에서 제외)')
    assert not attachment_has_eligibility_restriction('신청자격 및 공급대상에서 제외')
    assert attachment_has_eligibility_restriction('신청대상 : 경기도 거주자 제외')
    assert attachment_has_eligibility_restriction('중증 장애인만')

def test_hwpx_multiline_qualification_uses_only_qualification_section():
    text='신청자격 및 주택소유여부 확인대상자 :\n신청일 당시 경기도 거주 19세 이상\n장애인과 세대가 무주택인 자\n○ 선정방법 :\n건설시군 거주기간 점수'
    result=classify(text,'https://www.gg.go.kr/cmmn/download.do?idx=1')
    assert result['yongin_status']=='eligible' and result['disability_scope']=='both'

def test_yearless_real_period_has_bounded_reference_and_no_invented_time():
    text='○ 신청기간 : 9.14.~.9.18'
    assert parse_period(text)==(None,None)
    assert parse_period(text,'2026-09-08')==('2026-09-14','2026-09-18')
    assert parse_period(text,'2026-01-01')==(None,None)

def test_official_project_requires_location_not_similar_name():
    row=dict(HOUSE_NM='광명 시티프라디움 에듀하임',HSSPLY_ADRES='경기도 광명시 소하동 광명 구름산지구 도시개발사업지구 A6BL',HOUSE_MANAGE_NO='x',PBLANC_NO='y')
    listing=dict(name='시티프라디움 에듀하임',address='경기도 광명시 구름산지구 A6블록')
    assert same_project(listing,row)
    assert not same_project(dict(listing,address='경기도 광명시 구름산지구 A7블록'),row)
    assert not same_project(dict(listing,address='경기도 다른시 구름산지구 A6블록'),row)
    with pytest.raises(SourceError):select_project(listing,[row,row])

def test_filtered_pagination_uses_match_count_and_empty_page():
    class C:
        def __init__(self,payload):self.payload=payload;self.calls=0
        def request(self,*a,**kw):self.calls+=1;return json.dumps(self.payload)
    client=C(dict(data=[dict(HOUSE_NM='x')],totalCount=9000,matchCount=1))
    assert len(Applyhome(client,'test-key').get('getAPTLttotPblancDetail',{}))==1 and client.calls==1
    client=C(dict(data=[],totalCount=9000,matchCount=0))
    assert Applyhome(client,'test-key').get('getAPTLttotPblancDetail',{})==[] and client.calls==1

def test_vworld_round_trip_and_key_not_accepted_for_wrong_location():
    class C:
        def request(self,*a,**kw):
            assert kw['params']['key']=='test-key'
            return json.dumps({'response':{'status':'OK','refined':{'text':'경기도 용인시 기흥구 동백동 1','structure':{'level4LC':'4146311600'}},'result':{'point':{'x':'127.15','y':'37.26'}}}})
    geo=VWorld(C(),'test-key')
    loc=geo.locate('경기도 용인시 기흥구 동백동 1')
    assert loc['coordinates']==[37.26,127.15] and loc['lawd_codes']==['41463']
    with pytest.raises(SourceError,match='mismatch'):geo.locate('경기도 용인시 기흥구 동백동 2')
    with pytest.raises(SourceError,match='missing_vworld_key'):VWorld(C(),None).locate('x')

def test_live_catalog_fixture_has_no_secret_and_preserves_unit_identifiers():
    path=Path(__file__).parent/'fixtures/official-applyhome-2026-10-18.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    assert len(data['projects'])==9
    for row in data['projects']:
        assert row['models']
        for model in row['models']:
            assert str(model['HOUSE_MANAGE_NO'])==str(row['HOUSE_MANAGE_NO'])
            assert str(model['PBLANC_NO'])==str(row['PBLANC_NO'])
    assert 'serviceKey' not in path.read_text(encoding='utf-8')

def sample_notice():
    from scripts.collector import parse_notice
    html='<div class="s-v-board-default"><div class="k-content-padding">○ 공급위치 : 경기도 광주시 쌍령동 산54-29번지<br>○ 신청기간 : 2026.9.1 ~ 2026.9.7<br>○ 신청자격 : 경기도 거주 무주택 세대구성원 장애인</div></div>'
    return parse_notice(html,dict(B_IDX='1',SUBJECT='「실제회귀테스트」 장애인 특별공급 안내',WRITE_DATE2='2026-09-01'),NOW)

def test_announcement_only_change_keeps_dates_eligibility_and_source_id():
    first=sample_notice();change=deepcopy(first)
    change.update(id='gg_2',notice_url='https://www.gg.go.kr/bbs/boardView.do?bIdx=2',notice_updated_at='2026-09-10',
        address='광주시 쌍령동 산 54-29 번지',apply_start_at=None,apply_end_at=None)
    change['notice_history']=[dict(change['notice_history'][0],notice_url=change['notice_url'],content_sha256='c'*64,change_type='correction')]
    change['eligibility']=classify('발표일 연기','https://www.gg.go.kr')
    change['collection_issues']=['announcement_only_update']
    result=merge([first],[change],NOW)
    assert len(result)==1 and result[0]['id']==first['id']
    assert result[0]['apply_start_at']==first['apply_start_at']
    assert result[0]['eligibility']['yongin_status']=='eligible'
    assert len(result[0]['notice_history'])==2

def test_explicit_application_postponement_does_not_reopen_old_dates():
    first=sample_notice();change=deepcopy(first)
    change.update(notice_updated_at='2026-09-10',apply_start_at=None,apply_end_at=None)
    change['notice_history'][0].update(content_sha256='d'*64,change_type='correction')
    change['collection_issues']=['application_schedule_postponed']
    result=merge([first],[change],NOW)[0]
    assert result['apply_start_at'] is None and result['apply_end_at'] is None

def test_exact_official_house_type_area_only():
    assert official_type_area('084.9592A') == 84.9592
    assert official_type_area('084.0000B') == 84.0
    assert official_type_area(' 074.9845 ') == 74.9845
    assert official_type_area('84A') is None
    assert official_type_area('84') is None
    assert official_type_area('SUPLY_AR=111.4') is None
    assert official_type_area('084.9592A trailing-text') is None


def test_official_capture_enrichment_uses_verified_model_type_area(monkeypatch):
    from scripts.replay_catalog import CapturedApplyhome
    capture=json.loads((Path(__file__).parent/'fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))
    first=sample_notice();first.update(name='쌍용 더 플래티넘 한강',address='경기도 양평군 양서면 용담리 212-3번지 일원')
    unit=empty_unit('84A');unit['allocation_count']=1;first['units']=[unit]
    monkeypatch.delenv('VWORLD_API_KEY',raising=False)
    class NoNetwork:
        def request(self,*a,**kw):raise AssertionError('Replay must not request network or credentials')
    stats=enrich([first],NoNetwork(),NOW,dict(projects={},trade_locations={}),dict(version='test',approved=True),None,None,apply_client=CapturedApplyhome(capture))
    assert stats[2]==1
    assert first['units'][0]['sale_price_krw']==748000000
    assert first['units'][0]['area_sqm']==84.9947
    assert first['units'][0]['estimated_gap_krw'] is None
    assert first['housing_manage_no'] and first['pblanc_no']

def test_multiple_block_tables_keep_official_block_labels():
    tables=[[['신청형','배정 세대'],['84C','4']],[['신청형','배정 세대'],['84C','3']]]
    units=allocation_units(tables,['아크메르 동탄 95','아크메르 동탄 99'])
    assert [(u['type_id'],u['allocation_count']) for u in units]==[('아크메르 동탄 95:84C',4),('아크메르 동탄 99:84C',3)]

def test_zero_allocation_is_not_an_offered_unit():
    assert allocation_units([[['신청형','배정 세대'],['84C','0']]])==[]

def test_disability_allocation_required_for_calculation():
    from scripts.analysis import calculate
    u=empty_unit('84',84.9);u['sale_price_krw']=500000000
    result=calculate(u,[],{}, {},dict(version='test',approved=True),NOW.date())
    assert result['estimated_gap_krw'] is None and result['analysis_reason']=='disability_allocation_unverified'

def test_official_neighbor_district_query_covers_both_sides_of_border():
    class C:
        def request(self,url,**kw):
            assert url=='https://api.vworld.kr/req/data'
            assert kw['params']['data']=='LT_C_ADSIGG_INFO' and kw['params']['geomfilter'].startswith('BOX(')
            return json.dumps({'response':{'status':'OK','result':{'featureCollection':{'features':[
                {'properties':{'sig_cd':'41463','sig_kor_nm':'용인시기흥구'}},
                {'properties':{'sig_cd':'41465','sig_kor_nm':'용인시수지구'}}]}}}})
    assert set(VWorld(C(),'test-key').districts([37.3,127.1],2000))=={'41463','41465'}

def test_public_location_evidence_rejects_credentials(tmp_path):
    from scripts.location_evidence import write_locations
    data=dict(schema_version='1.0.0',generated_at=NOW.isoformat(),targets={'x':dict(coordinates=[37.2,127.1],
        evidence_url='https://www.vworld.kr/',checked_at=NOW.isoformat(),key='must-not-publish')},comparables={})
    with pytest.raises(ValueError,match='unexpected_location_field'):write_locations(tmp_path/'locations.json',data)
    assert not (tmp_path/'locations.json').exists()
