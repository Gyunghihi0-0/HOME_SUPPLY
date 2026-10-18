"""Kakao address verification. No credentials or raw responses are persisted."""
import json
import math
import re
from scripts.http_client import SourceError
from scripts.matching import address_key

SOURCE = 'https://developers.kakao.com/docs/ko/kakaomap/rest-api'

def normalized(address):
    text=re.sub(r'^경기\s+', '경기도 ', address or '')
    text=re.sub(r'^서울\s+', '서울특별시 ', text)
    text=re.sub(r'^인천\s+', '인천광역시 ', text)
    return address_key(text)

class Kakao:
    # Sampling detects nearby districts but cannot prove complete polygon coverage.
    coverage_complete = False

    def __init__(self, client, key):
        self.client, self.key = client, key
        self.memo = {}

    def get(self, path, params):
        if not self.key:
            raise SourceError('missing_kakao_key')
        try:
            raw = self.client.request('https://dapi.kakao.com/v2/local/' + path,
                params=params, headers={'Authorization': 'KakaoAK ' + self.key}, ttl=0)
            data = json.loads(raw)
            if not isinstance(data.get('documents'), list):
                raise SourceError('kakao_response_changed')
            return data['documents']
        except SourceError as exc:
            code = str(exc)
            raise SourceError(code if code.startswith('kakao_') else 'kakao_' + code) from None
        except (ValueError, TypeError):
            raise SourceError('kakao_response_changed') from None

    def locate(self, address):
        clean = re.sub(r'\([^)]*\)|\[[^]]*\]', '', address or '').strip()
        clean = re.sub(r'\s*일원\s*$', '', clean).replace('번지', '').strip()
        if clean in self.memo:
            return dict(self.memo[clean])
        if not re.search(r'\d', clean):
            raise SourceError('geocode_address_incomplete')
        docs = self.get('search/address.json', {'query': clean, 'analyze_type': 'exact', 'size': 30})
        matches = []
        for d in docs:
            addresses = [d.get('address') or {}, d.get('road_address') or {}]
            if not any(normalized(a.get('address_name')) == normalized(clean) for a in addresses):
                continue
            a = d.get('address') or {}
            try:
                lat, lon = float(d['y']), float(d['x'])
                code = a['b_code'][:5]
                if not (math.isfinite(lat) and math.isfinite(lon) and 33 <= lat <= 39 and 124 <= lon <= 132 and re.fullmatch(r'\d{5}', code)):
                    continue
                prefix = ' '.join([a['region_1depth_name'], a['region_2depth_name']])
                matches.append(dict(coordinates=[lat, lon], address=a['address_name'],
                    lawd_codes=[code], district_prefix=prefix, evidence_url=SOURCE))
            except (KeyError, TypeError, ValueError):
                continue
        if len(matches) != 1:
            raise SourceError('kakao_address_not_unique' if matches else 'kakao_exact_address_not_found')
        self.memo[clean] = matches[0]
        return dict(matches[0])

    def districts(self, coordinates, radius):
        lat, lon = coordinates
        dy = radius / 110000
        dx = dy / math.cos(math.radians(lat))
        prefixes = {}
        # Include the enclosing square as well as the center; exact distances are
        # still checked for every transaction. Never label this complete coverage.
        for yy in (-1, 0, 1):
            for xx in (-1, 0, 1):
                rows = self.get('geo/coord2regioncode.json', {'x': lon + xx*dx, 'y': lat + yy*dy})
                for row in rows:
                    if row.get('region_type') != 'B':
                        continue
                    code = str(row.get('code', ''))[:5]
                    prefix = ' '.join([row.get('region_1depth_name', ''), row.get('region_2depth_name', '')]).strip()
                    if re.fullmatch(r'\d{5}', code) and prefix:
                        prefixes[code] = prefix
        if not prefixes:
            raise SourceError('kakao_district_not_found')
        return prefixes
