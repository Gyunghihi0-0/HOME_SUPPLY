import hashlib
import json
from datetime import date
from decimal import Decimal
from defusedxml import ElementTree as ET
from scripts.http_client import SourceError

APPLYHOME='https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/'
MOLIT='https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade'
APPLY_SOURCE='https://www.data.go.kr/data/15098547/openapi.do'
TRADE_SOURCE='https://www.data.go.kr/data/15126469/openapi.do'

def won(value):
    if value is None or str(value).strip() in ('','-'):return None
    number=Decimal(str(value).replace(',','').strip())*10000
    if number<=0 or number!=number.to_integral_value():raise SourceError('invalid_price')
    return int(number)

class Applyhome:
    def __init__(self,client,key):self.client,self.key=client,key
    def get(self,endpoint,filters):
        if not self.key:raise SourceError('missing_applyhome_key')
        rows=[]
        for page in range(1,101):
            params=dict(page=page,perPage=100,serviceKey=self.key,**filters)
            try:d=json.loads(self.client.request(APPLYHOME+endpoint,params=params,ttl=20*3600))
            except (ValueError,KeyError):raise SourceError('applyhome_invalid_response') from None
            if not isinstance(d.get('data'),list) or 'totalCount' not in d:raise SourceError('applyhome_response_changed')
            rows.extend(d['data'])
            if len(rows)>=int(d['totalCount']):return rows
        raise SourceError('applyhome_pagination_limit')
    def project(self,mapping):
        filters={'cond[HOUSE_MANAGE_NO::EQ]':mapping['housing_manage_no'],'cond[PBLANC_NO::EQ]':mapping['pblanc_no']}
        rows=self.get('getAPTLttotPblancDetail',filters)
        if len(rows)!=1:raise SourceError('project_not_unique')
        row=rows[0]
        if str(row.get('HOUSE_MANAGE_NO'))!=mapping['housing_manage_no'] or str(row.get('PBLANC_NO'))!=mapping['pblanc_no']:
            raise SourceError('project_identifier_mismatch')
        normalize=lambda s:''.join(str(s).split())
        if normalize(row.get('HSSPLY_ADRES',''))!=normalize(mapping['official_address']):raise SourceError('project_address_mismatch')
        units=self.get('getAPTLttotPblancMdl',filters)
        if any(str(u.get('HOUSE_MANAGE_NO'))!=mapping['housing_manage_no'] or str(u.get('PBLANC_NO'))!=mapping['pblanc_no'] for u in units):
            raise SourceError('unit_project_mismatch')
        return row,units

class Molit:
    def __init__(self,client,key):self.client,self.key=client,key
    def month(self,lawd,month,now):
        if not self.key:raise SourceError('missing_molit_key')
        rows=[]
        for page in range(1,101):
            raw=self.client.request(MOLIT,params=dict(serviceKey=self.key,LAWD_CD=lawd,DEAL_YMD=month,pageNo=page,numOfRows=1000),ttl=20*3600)
            try:root=ET.fromstring(raw)
            except Exception:raise SourceError('molit_invalid_xml') from None
            if root.findtext('.//resultCode') not in ('000','00'):raise SourceError('molit_api_error')
            total=root.findtext('.//totalCount')
            if total is None:raise SourceError('molit_structure_changed')
            items=root.findall('.//items/item')
            rows.extend({c.tag:(c.text or '').strip() for c in item} for item in items)
            if page*1000>=int(total):break
            if not items:raise SourceError('molit_empty_page')
        else:raise SourceError('molit_pagination_limit')
        return normalize_trades(rows,lawd,now)

def normalize_trades(rows,lawd,now):
    result={}
    for row in rows:
        # Both cancellation indicator and cancellation date are authoritative.
        if row.get('cdealType') or row.get('cdealDay'):continue
        required=('aptNm','umdNm','jibun','excluUseAr','dealYear','dealMonth','dealDay','dealAmount','floor','buildYear')
        if any(not row.get(k) for k in required):continue
        if row.get('sggCd') and row['sggCd']!=lawd:raise SourceError('trade_region_mismatch')
        try:
            trade_date=date(int(row['dealYear']),int(row['dealMonth']),int(row['dealDay'])).isoformat()
            location='|'.join([lawd,row['umdNm'],row['jibun']])
            fingerprint='|'.join([location,row['aptNm'],row['excluUseAr'],trade_date,row['dealAmount'],row['floor']])
            ident=hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
            result[ident]=dict(id=ident,apartment_name=row['aptNm'],location=location,area_sqm=float(row['excluUseAr']),
                trade_date=trade_date,price_krw=won(row['dealAmount']),build_year=int(row['buildYear']),
                distance_m=None,source_url=TRADE_SOURCE,collected_at=now.isoformat())
        except (ValueError,ArithmeticError):raise SourceError('trade_value_changed') from None
    return list(result.values())

def empty_unit(type_id,area=None):
    return dict(type_id=type_id,area_sqm=area,allocation_count=None,sale_price_krw=None,sale_price_basis='unknown',
        sale_price_evidence_url=None,comparison_median_krw=None,estimated_gap_krw=None,gap_rate_pct=None,
        comparables_count=0,confidence='unavailable',analysis_reason='insufficient_verified_data',analysis_policy_version=None,comparables=[])
