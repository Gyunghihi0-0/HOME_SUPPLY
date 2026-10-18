"""Fixed read-only trade/coordinate capture; embedded inline, no repository checkout."""
import os,json,re,math,calendar,hashlib,time
from statistics import median
from decimal import Decimal
from datetime import datetime,date,timezone,timedelta
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

TARGETS = []  # Replaced with reviewed public target/model fields in the generated workflow.

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    now=datetime.now(timezone(timedelta(hours=9)));key=os.environ.get('MOLIT_SERVICE_KEY','').strip();kakao=os.environ.get('KAKAO_REST_API_KEY','').strip()
    if not key or not kakao:raise SystemExit('missing_secret')
    def get(url,params,headers=None):
        code='transport_error'
        for attempt in range(3):
            try:
                with build_opener(NoRedirect()).open(Request(url+'?'+urlencode(params),headers=headers or {}),timeout=25) as response:return response.read(15000000)
            except HTTPError as exc:
                code='http_'+str(exc.code)
                if exc.code not in (429,500,502,503,504):raise RuntimeError(code) from None
            except Exception:code='transport_error'
            time.sleep(attempt+1)
        raise RuntimeError(code) from None
    def local(path,params):return json.loads(get('https://dapi.kakao.com/v2/local/'+path,params,{'Authorization':'KakaoAK '+kakao}))['documents']
    districts=set();prefixes={}
    for target in TARGETS:
        lat,lon=target['coordinates'];dy=2000/110000;dx=dy/math.cos(math.radians(lat));codes=set()
        for yy in (-1,0,1):
            for xx in (-1,0,1):
                for row in local('geo/coord2regioncode.json',{'x':lon+xx*dx,'y':lat+yy*dy}):
                    if row.get('region_type')=='B':
                        codes.add(row['code'][:5]);prefixes[row['code'][:5]]=row['region_1depth_name']+' '+row['region_2depth_name']
        target['lawd_codes']=sorted(codes);districts.update(codes)
    print('TRADE_META '+json.dumps({'observed_at':now.isoformat(),'targets':TARGETS,'coverage':'nine_point_district_sampling_incomplete'},ensure_ascii=False),flush=True)
    locations=set();records=0;all_rows=[];failed_districts=set()
    oldest=now.date().replace(year=now.year-1,day=min(now.day,calendar.monthrange(now.year-1,now.month)[1]))
    month=oldest.replace(day=1)
    while month<=now.date():
        for district in sorted(districts):
            candidates=[t for t in TARGETS if district in t['lawd_codes']];rows=[];total=0;cancelled=0;invalid=0
            for page in range(1,31):
                try:raw=get('https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',{'serviceKey':key,'LAWD_CD':district,'DEAL_YMD':month.strftime('%Y%m'),'pageNo':page,'numOfRows':1000})
                except RuntimeError as exc:
                    failed_districts.add(district)
                    print('TRADE_MONTH_ERROR '+json.dumps({'district':district,'month':month.strftime('%Y%m'),'page':page,'code':str(exc)}),flush=True)
                    break
                root=ET.fromstring(raw)
                if root.findtext('.//resultCode') not in ('000','00'):raise RuntimeError('molit_application_error')
                total=int(root.findtext('.//totalCount'));items=root.findall('.//items/item')
                for item in items:
                    r={x.tag:(x.text or '').strip() for x in item}
                    required={'sggCd','umdNm','aptNm','jibun','excluUseAr','dealYear','dealMonth','dealDay','dealAmount','floor','buildYear','cdealType','cdealDay'}
                    if not required<=r.keys():invalid+=1;continue
                    if r.get('cdealType') or r.get('cdealDay'):cancelled+=1;continue
                    try:
                        area=float(r['excluUseAr']);year=int(r['buildYear']);day=date(int(r['dealYear']),int(r['dealMonth']),int(r['dealDay']))
                        amount=Decimal(r['dealAmount'].replace(',',''));floor=int(r['floor'])
                        if not (math.isfinite(area) and area>0 and 1900<=year<=now.year and amount.is_finite() and amount>0 and amount==amount.to_integral_value() and r['sggCd']==district):raise ValueError()
                    except Exception:invalid+=1;continue
                    if not oldest<=day<=now.date():continue
                    if not any(abs(year-t['build_year'])<=10 and any(abs(area/a-1)<=.10000001 for a in t['areas']) for t in candidates):continue
                    fields=['sggCd','umdNm','aptNm','jibun','excluUseAr','dealYear','dealMonth','dealDay','dealAmount','floor','buildYear','cdealType','cdealDay']
                    public={k:r.get(k,'') for k in fields};rows.append(public)
                    locations.add((r['sggCd'],r['umdNm'],r['jibun'],r['aptNm']))
                if page*1000>=total:break
            records+=len(rows);all_rows.extend(rows)
            print('TRADE_MONTH '+json.dumps({'district':district,'month':month.strftime('%Y%m'),'total':total,'cancelled':cancelled,'invalid':invalid,'candidate_count':len(rows)},ensure_ascii=False),flush=True)
        month=(month.replace(day=28)+timedelta(days=4)).replace(day=1)
    selected=sorted(locations)[:500]
    def locate(identity):
        code,dong,parcel,name=identity
        # Administrative prefix comes from the verified target's sampled district response.
        prefix=prefixes.get(code)
        if not prefix:return {'identity':identity,'error':'district_prefix_missing'}
        query=prefix+' '+dong+' '+parcel
        try:
            docs=local('search/address.json',{'query':query,'analyze_type':'exact','size':30})
            return {'identity':identity,'query':query,'documents':[{'x':d['x'],'y':d['y'],'address_name':(d.get('address') or {}).get('address_name'),'b_code':(d.get('address') or {}).get('b_code')} for d in docs]}
        except Exception:return {'identity':identity,'error':'geocode_transport_failure'}
    def normalized(value):
        value=re.sub(r'^경기\s+','경기도 ',value or '').replace('특례시','시')
        return re.sub(r'\s+|번지','',value)
    verified={}
    for result in ThreadPoolExecutor(max_workers=4).map(locate,selected):
        docs=[d for d in result.get('documents',[]) if normalized(d.get('address_name'))==normalized(result.get('query'))
              and str(d.get('b_code') or '').startswith(result['identity'][0])]
        if len(docs)==1:verified[tuple(result['identity'])]=[float(docs[0]['y']),float(docs[0]['x'])]
    def distance(a,b):
        lat1,lon1,lat2,lon2=map(math.radians,[a[0],a[1],b[0],b[1]])
        h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
        return 6371000*2*math.asin(min(1,math.sqrt(h)))
    i=now.year*12+now.month-1-6;year,month=divmod(i,12);month+=1
    recent=date(year,month,min(now.day,calendar.monthrange(year,month)[1]))
    for target in TARGETS:
        project_evidence={}
        for unit in target['units']:
            area=unit['area'];budget_missing=False
            candidates={}
            for r in all_rows:
                if r['sggCd'] not in target['lawd_codes'] or abs(int(r['buildYear'])-target['build_year'])>10 or abs(float(r['excluUseAr'])/area-1)>.1:continue
                identity=(r['sggCd'],r['umdNm'],r['jibun'],r['aptNm']);loc=verified.get(identity)
                if identity not in selected:budget_missing=True
                if not loc:continue
                dist=distance(target['coordinates'],loc)
                if dist>2000:continue
                day=date(int(r['dealYear']),int(r['dealMonth']),int(r['dealDay'])).isoformat()
                price=int(r['dealAmount'].replace(',',''))*10000
                fingerprint='|'.join([r['sggCd'],r['umdNm'],r['jibun'],r['aptNm'],str(float(r['excluUseAr'])),day,str(price),r['floor']])
                tid=hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
                candidates[tid]={'id':tid,'location':'|'.join(identity[:3]),'apartment_name':r['aptNm'],'area_sqm':float(r['excluUseAr']),
                    'build_year':int(r['buildYear']),'trade_date':day,'price_krw':price,'distance_m':round(dist,1),'coordinates':loc}
            values=list(candidates.values());last6=[r for r in values if r['trade_date']>=recent.isoformat()]
            chosen=last6 if len(last6)>=3 else values;mid=median([r['price_krw'] for r in chosen]) if chosen else None
            reason='sample_insufficient' if len(chosen)<3 else 'outlier_review_required' if max(abs(r['price_krw']-mid)/mid for r in chosen)>.5 else 'verified'
            if budget_missing:reason='geocode_budget_exhausted'
            if failed_districts.intersection(target['lawd_codes']):reason='trade_query_incomplete'
            for row in chosen:project_evidence[row['id']]=row
            print('TRADE_ANALYSIS '+json.dumps({'housing_manage_no':target['housing_manage_no'],'type':unit['type'],'area':area,'count':len(chosen),'price':unit['price'],
                'median':mid if reason=='verified' else None,'gap':mid-unit['price'] if reason=='verified' else None,
                'reason':reason,'window':6 if len(last6)>=3 else 12,'confidence':'low'},ensure_ascii=False),flush=True)
        sample=sorted(project_evidence.values(),key=lambda r:(r['trade_date'],r['id']))[:10]
        print('TRADE_PROJECT_EVIDENCE '+json.dumps({'housing_manage_no':target['housing_manage_no'],
            'sample':[{k:r[k] for k in ['apartment_name','trade_date','area_sqm','price_krw','build_year','distance_m']} for r in sample]},ensure_ascii=False),flush=True)
    print('TRADE_COMPLETE '+json.dumps({'rows':records,'unique_locations':len(locations),'attempted_locations':len(selected),'truncated':len(locations)>500,'failed_districts':sorted(failed_districts)}),flush=True)

if __name__=='__main__':main()
