"""Deterministic project matching: name + exact parcel/block, never fuzzy names."""
import re
from scripts.http_client import SourceError

def compact(value):return re.sub(r'[^가-힣A-Za-z0-9]','',value or '').upper()

def address_key(value):
    text=re.sub(r'\([^)]*\)|\[[^]]*\]','',value or '').replace('특례시','시')
    text=re.sub(r'^(?:경기도|인천광역시|서울특별시)\s*','',text)
    return re.sub(r'\s+|번지|일원|[,.]','',text)

def equivalent_location(a,b):
    if address_key(a)==address_key(b) and address_key(a):return True
    def parts(s):
        s=(s or '').replace('특례시','시')
        city=re.search(r'([가-힣]+(?:시|군))\s',s+' ')
        gu=re.search(r'([가-힣]+구)\s',s+' ')
        dong=re.search(r'([가-힣]+(?:동|리))\s*(산?\s*\d+(?:-\d+)?)',s)
        town=re.search(r'([가-힣]+(?:읍|면))\s',s+' ')
        tract=re.search(r'([가-힣]{2,})\s*지구',s)
        block=re.search(r'([A-Z]\d+(?:-\d+)?)\s*(?:BL|블록)',s,re.I)
        return city[1] if city else None,gu[1] if gu else None,(dong[1],compact(dong[2])) if dong else None,town[1] if town else None,tract[1] if tract else None,block[1].upper() if block else None
    x,y=parts(a),parts(b)
    if not x[0] or x[0]!=y[0] or (x[1] and y[1] and x[1]!=y[1]):return False
    if x[2] and x[2]==y[2] and x[3]==y[3]:return True
    return bool(x[4] and x[4]==y[4] and x[5] and x[5]==y[5])

def same_project(listing,row):
    a,b=compact(listing['name']),compact(row.get('HOUSE_NM'))
    if not a or not b or not (a==b or (len(a)>=6 and b.endswith(a))):return False
    x,y=address_key(listing['address']),address_key(row.get('HSSPLY_ADRES'))
    # Only equivalent complete locations. Discovery candidates are not matches.
    return bool(x and y and equivalent_location(listing['address'],row.get('HSSPLY_ADRES')))

def select_project(listing,rows):
    matches=[r for r in rows if same_project(listing,r)]
    if len(matches)!=1:raise SourceError('official_project_not_unique' if matches else 'official_project_not_matched')
    r=matches[0]
    if not r.get('HOUSE_MANAGE_NO') or not r.get('PBLANC_NO'):raise SourceError('project_identifier_missing')
    return r
