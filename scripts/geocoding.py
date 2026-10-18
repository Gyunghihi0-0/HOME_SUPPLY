"""Official VWorld geocoding; never invent coordinates or silently accept refinement."""
import json
import math
import re
from scripts.http_client import SourceError
from scripts.matching import address_key

SOURCE='https://www.vworld.kr/'
ENDPOINT='https://api.vworld.kr/req/address'

def require_success(response,fallback):
    if response.get('status')=='OK':return
    code=str(response.get('error',{}).get('code',''))
    if re.fullmatch(r'[A-Z_]{1,60}',code):raise SourceError('vworld_api_'+code)
    raise SourceError(fallback)

class VWorld:
    def __init__(self,client,key,domain=None):self.client,self.key,self.domain=client,key,domain
    def _request(self,endpoint,params,ttl):
        params=dict(params,key=self.key)
        if self.domain:params['domain']=self.domain
        try:return self.client.request(endpoint,params=params,ttl=ttl)
        except SourceError as exc:raise SourceError(str(exc) if str(exc).startswith('vworld_') else 'vworld_'+str(exc)) from None
    def locate(self,address):
        if not self.key:raise SourceError('missing_vworld_key')
        # Only already verified parcel/road addresses, not sales-center names or project-name search.
        clean=re.sub(r'\([^)]*\)','',address or '').strip()
        clean=re.sub(r'\s*일원\s*$','',clean)
        if not re.search(r'\d',clean):raise SourceError('geocode_address_incomplete')
        kind='ROAD' if re.search(r'(?:로|길)\s*\d',clean) else 'PARCEL'
        raw=self._request(ENDPOINT,dict(service='address',request='getcoord',version='2.0',crs='EPSG:4326',
            address=clean,format='json',type=kind,refine='false',simple='false'),86400)
        try:
            response=json.loads(raw)['response']
            require_success(response,'official_geocode_not_found')
            result=response['result'];point=result['point']
            lon,lat=float(point['x']),float(point['y'])
            if not math.isfinite(lon) or not math.isfinite(lat) or not (124<=lon<=132 and 33<=lat<=39):raise SourceError('geocode_coordinates_invalid')
            refined=response.get('refined',{})
            returned=refined.get('text') or result.get('text')
            # A result without round-trip address evidence is not verified.
            if not returned or address_key(returned)!=address_key(clean):raise SourceError('geocode_address_mismatch')
            structure=refined.get('structure') or result.get('structure') or {}
            lawd=str(structure.get('level4LC',''))[:5]
            prefix=re.match(r'^(.+?(?:구|군|시))\s+[가-힣]+(?:동|읍|면)',returned)
            return dict(coordinates=[lat,lon],evidence_url=SOURCE,lawd_codes=[lawd] if re.fullmatch(r'\d{5}',lawd) else [],
                address=returned,district_prefix=prefix[1] if prefix else None)
        except (ValueError,KeyError,TypeError):raise SourceError('geocode_response_changed') from None

    def districts(self,coordinates,radius):
        if not self.key:raise SourceError('missing_vworld_key')
        lat,lon=coordinates
        # Bounding rectangle covers the full radius. Trades are subsequently filtered by exact distance.
        dy=radius/110000;dx=dy/math.cos(math.radians(lat))
        params=dict(service='data',request='getfeature',version='2.0',data='LT_C_ADSIGG_INFO',format='json',
            size=100,page=1,geometry='false',attribute='true',crs='EPSG:4326',
            geomfilter=f'BOX({lon-dx},{lat-dy},{lon+dx},{lat+dy})')
        try:
            response=json.loads(self._request('https://api.vworld.kr/req/data',params,86400))['response']
            require_success(response,'official_district_query_failed')
            features=response['result']['featureCollection']['features']
            if not features or len(features)>=100:raise SourceError('official_district_coverage_incomplete')
            provinces={'11':'서울특별시','28':'인천광역시','41':'경기도'}
            prefixes={}
            for f in features:
                props=f['properties'];code=str(props['sig_cd'])
                prefix=props.get('full_nm')
                if not prefix and code[:2] in provinces:prefix=provinces[code[:2]]+' '+props['sig_kor_nm']
                if not re.fullmatch(r'\d{5}',code) or not prefix:raise SourceError('district_address_prefix_missing')
                prefixes[code]=prefix
            return prefixes
        except (ValueError,KeyError,TypeError):raise SourceError('district_response_changed') from None
