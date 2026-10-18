from copy import deepcopy
from datetime import datetime,date
import json
from pathlib import Path
import pytest
from scripts.analysis import calculate,months_before
from scripts.apis import empty_unit,normalize_trades,won
from scripts.collector import parse_notice,parse_period,status_at,KST,attachment_has_eligibility_restriction
from scripts.eligibility import classify
from scripts.http_client import SourceError
from scripts.pipeline import merge,run,atomic_write
from scripts.validate import validate

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,10,18,12,tzinfo=KST)

def notice():
    html='''<div class="s-v-board-default"><div class="k-content-padding">○ 공급위치 : 경기도 용인시 기흥구 테스트동 1<br>○ 신청기간 : ’26. 10. 27.(화) 09:00 ~ 11. 2.(월) 18:00<br>○ 신청자격 : 신청일 당시 경기도 거주 만19세 이상 무주택 세대구성원 장애인</div></div>'''
    return parse_notice(html,dict(B_IDX='1',SUBJECT='용인 「테스트」 장애인 특별공급 안내',WRITE_DATE2='2026-10-16'),NOW)

def test_period_and_status():
    n=notice()
    assert n['apply_start_at']=='2026-10-27T09:00:00+09:00'
    assert n['apply_end_at']=='2026-11-02T18:00:00+09:00'
    assert n['status']=='upcoming'
    assert status_at('2026-10-01','2026-10-18',NOW)=='unknown'
    assert status_at('2026-10-01','2026-10-17',NOW)=='closed'
    assert parse_period('청약접수 : 2026.10.1 ~ 2026.10.2')==(None,None)
    assert parse_period('신청기간 : 2026.13.1 ~ 2026.13.2')==(None,None)

def test_no_address_eligibility_inference():
    assert classify('공급위치 : 경기도 용인시','https://www.gg.go.kr')['yongin_status']=='unknown'
    assert classify('신청자격 : 서울시 거주 장애인','https://www.gg.go.kr')['yongin_status']=='unknown'
    assert notice()['eligibility']['disability_scope']=='both'
    text='신청자격 : 경기도 거주 중증 장애인만'
    assert classify(text,'https://www.gg.go.kr')['disability_scope']=='severe_only'
    assert classify('신청자격 : 경기도 거주 장애인 단, 예외 있음','https://www.gg.go.kr')['yongin_status']=='unknown'
    assert classify('장애정도 배점 중증 20 경증 10','https://www.gg.go.kr')['disability_scope']=='unknown'
    assert not attachment_has_eligibility_restriction('특별공급 건설시군 거주기간 점수 중증 20 경증 10')
    assert attachment_has_eligibility_restriction('신청대상 : 중증 장애인만')

def test_corrections_and_id_preservation():
    first=notice(); revised=deepcopy(first)
    revised['notice_history'][0]['content_sha256']='a'*64
    revised['apply_end_at']='2026-11-03'
    merged=merge([first],[revised],NOW)
    assert merged[0]['id']==first['id']
    assert len(merged[0]['notice_history'])==2
    assert len(merge(merged,[revised],NOW)[0]['notice_history'])==2
    assert len(merge([first],[],NOW))==1

def test_new_post_correction_keeps_id_but_followup_stays_separate():
    first=notice();correction=deepcopy(first)
    correction['id']='gg_2';correction['notice_updated_at']='2026-10-17'
    correction['notice_history'][0].update(notice_url='https://www.gg.go.kr/bbs/boardView.do?bIdx=2',content_sha256='b'*64,change_type='correction')
    correction['apply_end_at']='2026-11-04'
    merged=merge([first],[correction],NOW)
    assert len(merged)==1 and merged[0]['id']==first['id']
    assert merged[0]['apply_end_at']=='2026-11-04'
    followup=deepcopy(correction);followup['id']='gg_3';followup['notice_history'][0]['change_type']='initial'
    assert len(merge(merged,[followup],NOW))==2

def trade_rows():
    return [dict(aptNm='테스트',umdNm='테스트동',jibun='1',excluUseAr='84.9',dealYear='2026',dealMonth='10',dealDay='1',dealAmount='70,000',floor='5',buildYear='2020',sggCd='41463',cdealType='',cdealDay='')]

def test_won_cancel_and_duplicates():
    row=trade_rows()[0]
    assert won('70,000')==700000000
    assert won('-') is None
    assert len(normalize_trades([row,row],'41463',NOW))==1
    assert normalize_trades([dict(row,cdealType='O')],'41463',NOW)==[]
    assert normalize_trades([dict(row,cdealDay='20261002')],'41463',NOW)==[]

def analysis_inputs():
    u=empty_unit('84',84.9);u['sale_price_krw']=500000000
    t=normalize_trades(trade_rows(),'41463',NOW)[0]
    trades=[dict(t,id=str(i),price_krw=p) for i,p in enumerate([600000000,700000000,800000000])]
    loc={t['location']+'|'+t['apartment_name']:dict(coordinates=[37.25,127.1],evidence_url='https://www.gg.go.kr')}
    target=dict(coordinates=[37.25,127.1],build_year=2026,evidence_url='https://www.gg.go.kr')
    policy=json.loads((ROOT/'config/analysis.json').read_text())
    return u,trades,target,loc,policy

def test_calculation_and_missing_evidence():
    u,t,target,loc,p=analysis_inputs()
    r=calculate(u,t,target,loc,p,NOW.date())
    assert r['comparison_median_krw']==700000000
    assert r['estimated_gap_krw']==200000000
    assert r['gap_rate_pct']==40
    assert r['comparables_count']==3
    for changes in [dict(sale_price_krw=None),dict(area_sqm=None)]:
        assert calculate(dict(u,**changes),t,target,loc,p,NOW.date())['estimated_gap_krw'] is None
    assert calculate(u,t[:2],target,loc,p,NOW.date())['estimated_gap_krw'] is None
    assert calculate(u,t,target,{},p,NOW.date())['estimated_gap_krw'] is None
    far=deepcopy(loc)
    next(iter(far.values()))['coordinates']=[38.25,127.1]
    assert calculate(u,t,target,far,p,NOW.date())['estimated_gap_krw'] is None
    old=[dict(x,build_year=2000) for x in t]
    assert calculate(u,old,target,loc,p,NOW.date())['estimated_gap_krw'] is None

def test_twelve_month_fallback_and_outlier_hold():
    u,t,target,loc,p=analysis_inputs()
    older=[dict(x,trade_date='2026-02-01') for x in t]
    assert calculate(u,older,target,loc,p,NOW.date())['analysis_reason']=='extended_to_twelve_months'
    outliers=t+[dict(t[0],id='expensive',price_krw=2000000000)]
    assert calculate(u,outliers,target,loc,p,NOW.date())['analysis_reason']=='outlier_review_required'
    assert months_before(date(2024,8,31),6)==date(2024,2,29)

class BrokenClient:
    def request(self,*a,**kw):raise SourceError('http_503')

def test_failure_preserves_previous_data_and_last_success(tmp_path,monkeypatch):
    monkeypatch.delenv('APPLYHOME_SERVICE_KEY',raising=False);monkeypatch.delenv('MOLIT_SERVICE_KEY',raising=False)
    output=tmp_path/'latest.json'
    data=dict(schema_version='1.0.0',generated_at=NOW.isoformat(),last_success_at=NOW.isoformat(),data_status='ok',sources=[],listings=[notice()])
    atomic_write(output,data)
    assert run(output,client=BrokenClient(),now=NOW)==1
    result=json.loads(output.read_text(encoding='utf-8'))
    assert result['last_success_at']==data['last_success_at']
    assert result['listings'][0]['id']=='gg_1'
    assert result['data_status']=='stale'
    validate(result)

def test_invalid_output_does_not_overwrite(tmp_path):
    path=tmp_path/'latest.json';path.write_text('preserve')
    with pytest.raises(Exception):atomic_write(path,{'bad':True})
    assert path.read_text()=='preserve'

def test_schema_rejects_timezone_missing_and_unknown_field():
    data=dict(schema_version='1.0.0',generated_at='2026-10-18T12:00:00',last_success_at=None,data_status='error',sources=[],listings=[])
    with pytest.raises(Exception):validate(data)
    data['generated_at']=NOW.isoformat();data['secret']='forbidden'
    with pytest.raises(Exception):validate(data)
