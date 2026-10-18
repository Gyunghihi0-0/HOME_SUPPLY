"""Offline matching experiments on captured public API data; never publish guesses."""
import json
from pathlib import Path
from difflib import SequenceMatcher
from scripts.matching import compact, same_project, equivalent_location
from scripts.structured import normalize_type

ROOT=Path(__file__).resolve().parents[1]

def audit():
    data=json.loads((ROOT/'docs/data/latest.json').read_text(encoding='utf-8'))
    capture=json.loads((ROOT/'tests/backend/fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))
    report=[]
    for item in data['listings']:
        name=compact(item['name'])
        pairs=[]
        for row in capture['projects']:
            official=compact(row['HOUSE_NM'])
            overlap=name in official or official in name
            similarity=SequenceMatcher(None,name,official).ratio()
            exact=same_project(item,row)
            if not (overlap or similarity>=.55 or exact):continue
            units=[]
            for unit in item['units']:
                context,sep,label=unit['type_id'].rpartition(':')
                label=label if sep else unit['type_id']
                context_match=not sep or compact(context)==official
                models=[m for m in row['models'] if context_match and normalize_type(label) is not None
                        and normalize_type(label)==normalize_type(m['HOUSE_TY'])]
                if len(models)==1:
                    units.append({'notice_type':unit['type_id'],'official_type':models[0]['HOUSE_TY'],
                                  'maximum_price_10k':models[0]['LTTOT_TOP_AMOUNT']})
            pairs.append({'official_name':row['HOUSE_NM'],'official_address':row['HSSPLY_ADRES'],
                          'housing_manage_no':row['HOUSE_MANAGE_NO'],'publication_date':row['RCRIT_PBLANC_DE'],
                          'current_match':exact,'literal_search_can_find':item['name'] in row['HOUSE_NM'],
                          'name_containment':overlap,'name_similarity':round(similarity,3),
                          'address_match':equivalent_location(item['address'],row['HSSPLY_ADRES']),
                          'context_scoped_exact_types':units})
        report.append({'notice_id':item['id'],'name':item['name'],'address':item['address'],
                       'notice_url':item['notice_url'],'candidates':pairs,
                       'status':'matched' if any(p['current_match'] for p in pairs) else
                       'candidate_requires_review' if pairs else 'not_in_filtered_capture'})
    counts={status:sum(r['status']==status for r in report) for status in
            ('matched','candidate_requires_review','not_in_filtered_capture')}
    output={'capture_source':capture['verification_run'],'capture_projects':len(capture['projects']),
            'notice_count':len(report),'counts':counts,
            'limitation':'120-day API catalog filtered by name containment before capture; absence is not proof of unpublished price.',
            'listings':report}
    path=ROOT/'handoff/matching-audit.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))
    for r in report:
        if r['status']=='candidate_requires_review':print(json.dumps(r,ensure_ascii=False))
    print('Exact project matches missed by literal query:',sum(p['current_match'] and not p['literal_search_can_find'] for r in report for p in r['candidates']))

if __name__=='__main__':audit()
