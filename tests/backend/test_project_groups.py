import json
from copy import deepcopy
from pathlib import Path
from scripts.project_groups import expand_projects, grouped_location
from scripts.matching import select_project
from scripts.apis import Applyhome

ROOT=Path(__file__).resolve().parents[2]

def inputs():
    return (json.loads((ROOT/'tests/backend/fixtures/grouped-notices.json').read_text(encoding='utf-8')),
            json.loads((ROOT/'tests/backend/fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))['projects'])

def test_real_capture_split_is_scoped_and_repeatable():
    items,rows=inputs()
    expanded=expand_projects(items,rows)
    ark=[x for x in expanded if x['name']=='아크메르 동탄 95'][0]
    assert [u['type_id'] for u in ark['units']]==['84C','84F']
    parent=next(x for x in expanded if x['id']=='gg_266126622')
    assert all('99:' in u['type_id'] for u in parent['units'])
    blocks=[x for x in expanded if x['name'].startswith('힐스테이트 고덕엘리스트')]
    assert len(blocks)==2
    assert {select_project(x,rows)['HOUSE_MANAGE_NO'] for x in blocks}=={'2026000437','2026000438'}
    assert all(not x['units'] for x in blocks)  # no fabricated disability allocations
    assert expand_projects(expanded,rows)==expanded
    again=expand_projects(items+expanded,rows)
    assert len({x['id'] for x in again})==len(again)

def test_ambiguous_project_and_wrong_city_not_split():
    items,rows=inputs()
    rows=deepcopy(rows)
    rows.append(dict(rows[0],PBLANC_NO='another'))
    assert not any(x['name']=='아크메르 동탄 95' for x in expand_projects(items,rows))
    for row in rows:
        if '고덕엘리스트' in row['HOUSE_NM']:row['HSSPLY_ADRES']=row['HSSPLY_ADRES'].replace('평택시','용인시')
    assert len([x for x in expand_projects(items,rows) if x['name'].startswith('힐스테이트 고덕엘리스트')])==1

def test_catalog_query_has_no_name_filter_and_is_reused():
    class Probe(Applyhome):
        def __init__(self):self.calls=[]
        def get(self,endpoint,filters):self.calls.append((endpoint,filters));return []
    client=Probe()
    client.catalog();client.catalog()
    assert len(client.calls)==1
    assert set(client.calls[0][1])=={'cond[RCRIT_PBLANC_DE::GTE]'}

def test_parcel_list_handles_second_parcel_without_accepting_neighbor():
    source='화성특례시 동탄구 반송동 95, 99 번지'
    assert grouped_location(source,'경기도 화성특례시 동탄구 반송동 99번지')
    assert not grouped_location(source,'경기도 화성특례시 동탄구 반송동 96번지')
    assert not grouped_location(source,'경기도 수원시 동탄구 반송동 99번지')

def test_refresh_merge_does_not_collapse_sibling_projects():
    from scripts.pipeline import merge
    from tests.backend.test_pipeline import NOW
    items,rows=inputs()
    expanded=expand_projects(items,rows)
    merged=merge(expanded,[],NOW)
    assert {x['id'] for x in merged}=={x['id'] for x in expanded}
