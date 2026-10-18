"""Deterministic project matching: name + exact parcel/block, never fuzzy names."""
import re
from scripts.http_client import SourceError


def blocks(value):
    return {re.sub(r'[-\s]','',m.upper()) for m in re.findall(r'(?<![A-Za-z0-9])([A-Za-z]{0,3}\s*-?\s*\d+(?:-\d+)?)\s*(?:BL|블록)',value or '',re.I)}


def canonical_name(value):
    value=(value or '').replace('&','앤').replace('＆','앤')
    value=re.sub(r'장애인\s*특별공급\s*안내|공공분양주택|\(?본청약\)?','',value)
    value=re.sub(r'지구','',value)
    return compact(value)


def tract(value):
    value=re.sub(r'\s+','',value or '')
    m=re.search(r'([가-힣0-9]+?)(?:공공주택|택지개발|도시개발사업|도시개발|국제화계획)?지구',value)
    if not m:return None
    result=re.split(r'일원|및|[,()]',m[1])[-1]
    result=re.sub(r'^(?:경기도|인천광역시|서울특별시)','',result)
    result=result.split('시')[-1] if '시' in result else result
    return result.replace('테크노밸리','')


def strong_location(listing,row):
    a,b=listing.get('address') or '',row.get('HSSPLY_ADRES') or ''
    if equivalent_location(a,b):return True
    # A shared development name/block cannot override contradictory municipalities.
    for suffix in ('시|군','구'):
        left=re.search(r'([가-힣]+(?:'+suffix+r'))\s',a.replace('특례시','시')+' ')
        right=re.search(r'([가-힣]+(?:'+suffix+r'))\s',b.replace('특례시','시')+' ')
        if left and right and left[1]!=right[1]:return False
    x,y=blocks(a),blocks(b)
    if len(x)!=1 or x!=y:return False
    ta,tb=tract(a),tract(b)
    # Incomplete block addresses such as 인천계양 A6 are accepted only when
    # the exact official tract identity is also present, never just A6.
    if ta is None:
        short=re.sub(r'\s+','',a)
        ta=re.sub(r'[A-Za-z]{0,3}-?\d+(?:-\d+)?(?:BL|블록).*','',short,flags=re.I)
    return bool(ta and tb and (ta==tb or ta.endswith(tb)))

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
    a,b=canonical_name(listing['name']),canonical_name(row.get('HOUSE_NM'))
    if not a or not b or not (a==b or (len(a)>=6 and b.endswith(a))):return False
    x,y=address_key(listing['address']),address_key(row.get('HSSPLY_ADRES'))
    # Only equivalent complete locations. Discovery candidates are not matches.
    # Explicit phase or block disagreement is never repaired by fuzzy names.
    left,right=blocks(listing['name']+' '+(listing.get('address') or '')),blocks((row.get('HOUSE_NM') or '')+' '+(row.get('HSSPLY_ADRES') or ''))
    if left and right and left.isdisjoint(right):return False
    return bool(x and y and strong_location(listing,row))


def candidate_diagnosis(listing,rows):
    name=canonical_name(listing['name'])
    named=[r for r in rows if name==canonical_name(r.get('HOUSE_NM')) or (len(name)>=6 and name in canonical_name(r.get('HOUSE_NM')))]
    located=[r for r in rows if strong_location(listing,r)]
    if located and not named:return 'official_project_name_mismatch'
    if named:
        source=blocks(listing['name']+' '+(listing.get('address') or ''))
        if source and all(blocks((r.get('HOUSE_NM') or '')+' '+(r.get('HSSPLY_ADRES') or '')) and source.isdisjoint(blocks((r.get('HOUSE_NM') or '')+' '+(r.get('HSSPLY_ADRES') or ''))) for r in named):
            return 'official_project_block_mismatch'
        return 'official_project_address_mismatch'
    return 'official_project_not_in_catalog'

def select_project(listing,rows):
    identities=[r for r in rows if listing.get('housing_manage_no') and listing.get('pblanc_no') and str(r.get('HOUSE_MANAGE_NO'))==listing['housing_manage_no'] and str(r.get('PBLANC_NO'))==listing['pblanc_no']]
    matches=identities or [r for r in rows if same_project(listing,r)]
    if identities and not strong_location(listing,identities[0]):raise SourceError('official_project_address_mismatch')
    if len(matches)!=1:raise SourceError('official_project_multiple_candidates' if matches else candidate_diagnosis(listing,rows))
    r=matches[0]
    if not r.get('HOUSE_MANAGE_NO') or not r.get('PBLANC_NO'):raise SourceError('project_identifier_missing')
    return r
