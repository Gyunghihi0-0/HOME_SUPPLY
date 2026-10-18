"""Standalone allowlisted evidence capture, embedded inline in a no-checkout job."""
import os,json,re,time,math
from datetime import datetime,timedelta,timezone
from difflib import SequenceMatcher
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlencode
from urllib.error import HTTPError,URLError
from xml.etree import ElementTree as ET

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    opener=build_opener(NoRedirect())
    def get(url,params=None,headers=None):
        request=Request(url+('?' + urlencode(params) if params else ''),headers=headers or {})
        try:
            with opener.open(request,timeout=25) as response:return response.read(10000000)
        except HTTPError as exc:raise RuntimeError('http_'+str(exc.code)) from None
        except URLError:raise RuntimeError('network_error') from None
        except Exception:raise RuntimeError('transport_error') from None
    key=os.environ.get('APPLYHOME_SERVICE_KEY','').strip()
    if not key:raise SystemExit('missing_applyhome_key')
    now=datetime.now(timezone(timedelta(hours=9)))
    base='https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/'
    def api(endpoint,filters):
        rows=[]
        for page in range(1,51):
            response=json.loads(get(base+endpoint,dict(page=page,perPage=100,serviceKey=key,**filters)))
            if not isinstance(response.get('data'),list):raise RuntimeError('response_shape')
            rows.extend(response['data'])
            if len(rows)>=int(response.get('matchCount',response['totalCount'])) or len(response['data'])<100:return rows
        raise RuntimeError('pagination_limit')
    catalog=api('getAPTLttotPblancDetail',{'cond[RCRIT_PBLANC_DE::GTE]':(now.date()-timedelta(days=365)).isoformat()})
    fields=['HOUSE_MANAGE_NO','PBLANC_NO','HOUSE_NM','HSSPLY_ADRES','RCRIT_PBLANC_DE','MVN_PREARNGE_YM','HOUSE_DTL_SECD','PBLANC_URL']
    labels=['아르뮤제이','광교 자연앤 센트레빌','안산신길2','한화포레나 지제역','시흥 거모','구리갈매역세권','고덕 우미 린','계양신도시 카이브 유보라','경기광주역 롯데캐슬','엘리프 시흥','중앙하이츠 구성','부천대장','아크메르 동탄','향남 롯데캐슬','GTX운정중앙역 시티프라디움','청라 아크원','향남역 그로브','쌍용 더 플래티넘 한강','화서역 호수공원','시티프라디움 에듀하임','검단 센트레빌','중동역 다채로움','인천계양','동백호수공원','힐스테이트 고덕엘리스트','더샵 분당','산곡역자이']
    norm=lambda s:re.sub(r'[^가-힣A-Za-z0-9]','',s or '').upper()
    candidates=[]
    print('EVIDENCE_META '+json.dumps({'observed_at':now.isoformat(),'catalog_complete':True,'cutoff':(now.date()-timedelta(days=365)).isoformat()},ensure_ascii=False),flush=True)
    for row in catalog:
        public={k:row.get(k) for k in fields}
        # Output every metadata row. Name similarity only expands model retrieval, never confirms a match.
        plausible=any(norm(label) in norm(row['HOUSE_NM']) or norm(row['HOUSE_NM']) in norm(label)
                      or SequenceMatcher(None,norm(label),norm(row['HOUSE_NM'])).ratio()>.48 for label in labels)
        if plausible:
            models=api('getAPTLttotPblancMdl',{'cond[HOUSE_MANAGE_NO::EQ]':row['HOUSE_MANAGE_NO'],'cond[PBLANC_NO::EQ]':row['PBLANC_NO']})
            public['models']=[{k:m.get(k) for k in ['HOUSE_MANAGE_NO','PBLANC_NO','MODEL_NO','HOUSE_TY','LTTOT_TOP_AMOUNT','SUPLY_AR']} for m in models]
            candidates.append(public)
        print('EVIDENCE_PROJECT '+json.dumps(public,ensure_ascii=False),flush=True)
    kkey=os.environ.get('KAKAO_REST_API_KEY','').strip()
    if kkey:
        for row in candidates:
            address=re.sub(r'\([^)]*\)|\[[^]]*\]','',row['HSSPLY_ADRES']).replace('번지','').strip()
            address=re.sub(r'\s*일원\s*$','',address)
            try:
                response=json.loads(get('https://dapi.kakao.com/v2/local/search/address.json',{'query':address,'analyze_type':'exact','size':30},{'Authorization':'KakaoAK '+kkey}))
                documents=[]
                for d in response.get('documents',[]):
                    a=d.get('address') or {}
                    documents.append({'x':d.get('x'),'y':d.get('y'),'address':{k:a.get(k) for k in ['address_name','b_code','region_1depth_name','region_2depth_name','region_3depth_name']},'road_address':{'address_name':(d.get('road_address') or {}).get('address_name')}})
                print('EVIDENCE_GEOCODE '+json.dumps({'housing_manage_no':row['HOUSE_MANAGE_NO'],'query':address,'documents':documents},ensure_ascii=False),flush=True)
            except Exception as exc:print('EVIDENCE_GEOCODE_ERROR '+json.dumps({'housing_manage_no':row['HOUSE_MANAGE_NO'],'code':str(exc) if isinstance(exc,RuntimeError) else 'parse_error'}),flush=True)
    print('EVIDENCE_COMPLETE '+str(len(catalog)),flush=True)

if __name__=='__main__':main()
