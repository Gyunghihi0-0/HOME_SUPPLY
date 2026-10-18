import json
import pytest
from datetime import datetime
from scripts.apis import Applyhome,Molit
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
