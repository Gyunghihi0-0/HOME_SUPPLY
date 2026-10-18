"""Split explicitly grouped notices; never pool prices across blocks/projects."""
import re
from copy import deepcopy
from scripts.matching import compact, equivalent_location


def blocks(text):
    return set(re.findall(r'(?<![A-Z0-9])([A-Z]{1,3}-?\d+(?:-\d+)?)\s*(?:BL|블록)',(text or '').upper()))


def base_name(text):
    text=re.sub(r'[A-Z]{1,3}-?\d+(?:-\d+)?\s*(?:BL|블록)','',text,flags=re.I)
    return compact(re.sub(r'공공분양주택|장애인\s*특별공급\s*안내','',text))


def grouped_location(address,official):
    # Explicit parcel lists, e.g. 반송동 95, 99번지; never turn 95 into 99 by name alone.
    match=re.search(r'([가-힣]+(?:동|리))\s*((?:\d+(?:-\d+)?\s*,\s*)+\d+(?:-\d+)?)\s*번지',address or '')
    if not match:return equivalent_location(address,official)
    return any(equivalent_location(address[:match.start(2)]+parcel.strip()+address[match.end(2):],official)
               for parcel in match[2].split(','))


def expand_projects(items,catalog):
    result=[]
    refreshed={}
    for item in items:
        contexts={u['type_id'].rsplit(':',1)[0] for u in item['units'] if ':' in u['type_id']}
        source_blocks=blocks(item['address'])
        if not contexts and len(source_blocks)<2:
            result.append(item);continue
        groups=[]
        if contexts:
            for context in sorted(contexts):
                candidates=[r for r in catalog if compact(r['HOUSE_NM'])==compact(context)
                            and grouped_location(item['address'],r['HSSPLY_ADRES'])]
                if len(candidates)==1:
                    units=[u for u in item['units'] if u['type_id'].startswith(context+':')]
                    groups.append((candidates[0],units,context))
        else:
            city=re.search(r'([가-힣]+(?:시|군))\s',item['address'] or '')
            for block in sorted(source_blocks):
                candidates=[r for r in catalog if blocks(r['HOUSE_NM']+' '+r['HSSPLY_ADRES'])=={block}
                            and base_name(r['HOUSE_NM'])==base_name(item['name'])
                            and city and city[1] in r['HSSPLY_ADRES']]
                if len(candidates)==1:groups.append((candidates[0],[],block))
        used=set()
        for row,units,context in groups:
            child=deepcopy(item)
            child.update(id=item['id']+'_p'+str(row['HOUSE_MANAGE_NO'])+'_'+str(row['PBLANC_NO']),
                         name=row['HOUSE_NM'],address=row['HSSPLY_ADRES'],
                         housing_manage_no=None,pblanc_no=None,location_verified=False)
            child['units']=[]
            for original in units:
                u=deepcopy(original);used.add(original['type_id'])
                u['type_id']=u['type_id'].rsplit(':',1)[-1]
                child['units'].append(u)
            child['collection_issues']=sorted(set(child['collection_issues']+['grouped_notice_project_split']))
            result.append(child)
            refreshed[child['id']]=child
        remaining=[u for u in item['units'] if u['type_id'] not in used]
        if not groups or remaining or (not contexts and len(groups)!=len(source_blocks)):
            remainder=deepcopy(item);remainder['units']=remaining
            result.append(remainder)
    unique={r['id']:r for r in result}
    unique.update(refreshed)
    return list(unique.values())
