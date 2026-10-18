import json
import pytest
from datetime import datetime
from scripts.apis import Applyhome,Molit,MOLIT,MOLIT_GENERAL,TRADE_SOURCE,TRADE_GENERAL_SOURCE,normalize_trades
from scripts.http_client import Client,SourceError
from scripts.collector import KST
NOW=datetime(2026,10,18,12,tzinfo=KST)

class FakeClient:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs));return next(self.responses)

def test_applyhome_uses_both_identifiers_and_address():
    row=dict(HOUSE_MANAGE_NO='20260001',PBLANC_NO='20260002',HSSPLY_ADRES='경기도 용인시 테스트동 1')
    model=dict(HOUSE_MANAGE_NO='20260001',PBLANC_NO='20260002',MODEL_NO='01')
    client=FakeClient([json.dumps(dict(data=[row],totalCount=1)),json.dumps(dict(data=[model],totalCount=1))])
    mapping=dict(housing_manage_no='20260001',pblanc_no='20260002',official_address=row['HSSPLY_ADRES'])
    assert Applyhome(client,'secret').project(mapping)[1]==[model]
    params=client.calls[0][1]['params']
    assert params['cond[HOUSE_MANAGE_NO::EQ]']=='20260001'
    assert params['cond[PBLANC_NO::EQ]']=='20260002'
    wrong=FakeClient([json.dumps(dict(data=[dict(row,HSSPLY_ADRES='서울특별시')],totalCount=1))])
    with pytest.raises(SourceError,match='address_mismatch'):Applyhome(wrong,'secret').project(mapping)

def test_no_key_never_calls_api():
    c=FakeClient([])
    with pytest.raises(SourceError,match='missing_applyhome_key'):Applyhome(c,None).get('x',{})
    with pytest.raises(SourceError,match='missing_molit_key'):Molit(c,None).month('41463','202610',NOW)
    assert c.calls==[]

def test_application_error_is_not_empty_success():
    c=FakeClient([b'<response><header><resultCode>30</resultCode></header></response>'])
    with pytest.raises(SourceError,match='api_error'):Molit(c,'secret').month('41463','202610',NOW)

def test_robot_paths_and_wildcards():
    c=Client(pause=0)
    c.robots['https://www.gg.go.kr']=[('/common/',False),('/*.xml$',False),('/sitemap.xml',True)]
    c.check_robots('https://www.gg.go.kr/cmmn/download.do?idx=1')
    c.check_robots('https://www.gg.go.kr/sitemap.xml')
    with pytest.raises(SourceError):c.check_robots('https://www.gg.go.kr/common/file')
    with pytest.raises(SourceError):c.check_robots('https://www.gg.go.kr/private.xml')

def trade_row():
    return dict(sggCd='41463',aptNm='테스트',umdNm='테스트동',jibun='1',excluUseAr='84.90',dealYear='2026',dealMonth='10',dealDay='1',dealAmount='70,000',floor='5',buildYear='2020',cdealType='',cdealDay='')

def xml_response(rows):
    from xml.etree.ElementTree import Element,SubElement,tostring
    root=Element('response');SubElement(SubElement(root,'header'),'resultCode').text='000'
    body=SubElement(root,'body');SubElement(body,'totalCount').text=str(len(rows));items=SubElement(body,'items')
    for row in rows:
        item=SubElement(items,'item')
        for k,v in row.items():SubElement(item,k).text=v
    return tostring(root)

def test_detail_default_and_field_units():
    c=FakeClient([xml_response([trade_row()])]);api=Molit(c,'secret')
    result=api.month('41463','202610',NOW)
    assert c.calls[0][0][0]==MOLIT
    assert result[0]['price_krw']==700000000 and result[0]['area_sqm']==84.9
    assert result[0]['trade_date']=='2026-10-01' and result[0]['build_year']==2020
    assert result[0]['source_url']==TRADE_SOURCE
    # Floor is validated and used for deduplication, not published with unit/dong information.
    assert 'floor' not in result[0]
    with pytest.raises(SourceError,match='trade_value_changed'):
        normalize_trades([dict(trade_row(),floor='invalid')],'41463',NOW)

@pytest.mark.parametrize('field',['dealAmount','excluUseAr','dealYear','dealMonth','dealDay','floor','buildYear','cdealType','cdealDay'])
def test_required_field_missing_is_explicit(field):
    row=trade_row();del row[field]
    c=FakeClient([xml_response([row])])
    with pytest.raises(SourceError,match='trade_required_fields_missing'):Molit(c,'secret').month('41463','202610',NOW)
    assert len(c.calls)==1

def test_optional_fallback_replaces_month_and_tracks_source():
    row=trade_row();del row['floor']
    c=FakeClient([xml_response([row]),xml_response([trade_row()])]);api=Molit(c,'detail-test-key',allow_general_fallback=True,general_key='general-test-key')
    result=api.month('41463','202610',NOW)
    assert [x[0][0] for x in c.calls]==[MOLIT,MOLIT_GENERAL]
    assert len(result)==1 and result[0]['source_url']==TRADE_GENERAL_SOURCE and api.fallback_used
    assert c.calls[0][1]['params']['serviceKey']=='detail-test-key'
    assert c.calls[1][1]['params']['serviceKey']=='general-test-key'

def test_general_key_is_required_and_never_reuses_detail_key():
    c=FakeClient([])
    with pytest.raises(SourceError,match='missing_molit_general_key'):
        Molit(c,'detail-test-key').general_month('41463','202610',NOW)
    assert c.calls==[]
    row=trade_row();del row['floor']
    c=FakeClient([xml_response([row])])
    with pytest.raises(SourceError,match='missing_molit_general_key'):
        Molit(c,'detail-test-key',allow_general_fallback=True).month('41463','202610',NOW)
    assert len(c.calls)==1

def test_general_probe_can_run_independently_of_detail_key():
    c=FakeClient([xml_response([trade_row()])])
    result=Molit(c,None,general_key='general-test-key').general_month('41463','202610',NOW)
    assert c.calls[0][0][0]==MOLIT_GENERAL
    assert c.calls[0][1]['params']['serviceKey']=='general-test-key'
    assert result[0]['source_url']==TRADE_GENERAL_SOURCE

def test_empty_or_auth_failure_does_not_fallback():
    c=FakeClient([xml_response([])]);api=Molit(c,'secret',allow_general_fallback=True)
    assert api.month('41463','202610',NOW)==[] and len(c.calls)==1
    c=FakeClient([b'<response><header><resultCode>30</resultCode></header></response>'])
    with pytest.raises(SourceError,match='molit_api_error'):Molit(c,'secret',allow_general_fallback=True).month('41463','202610',NOW)
    assert len(c.calls)==1

def test_official_spec_includes_all_analysis_fields():
    from pathlib import Path
    spec=json.loads((Path(__file__).resolve().parents[2]/'config/molit-15126468-fields.json').read_text(encoding='utf-8'))
    assert spec['endpoint']==MOLIT
    assert {'dealAmount','excluUseAr','dealYear','dealMonth','dealDay','floor','buildYear','cdealType','cdealDay'}<=spec['fields'].keys()
    assert spec['fields']['dealAmount']=='거래금액(만원)'
