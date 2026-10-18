from scripts.price_ranges import family_price
from scripts.analysis import calculate
from scripts.apis import empty_unit
from tests.backend.test_pipeline import analysis_inputs, NOW
from scripts.pipeline import enrich
from tests.backend.test_pipeline import notice, BrokenClient
from scripts.validate import validate


def models():
    return [dict(MODEL_NO='1',HOUSE_TY='084.9000A',LTTOT_TOP_AMOUNT='70,000'),
            dict(MODEL_NO='2',HOUSE_TY='084.8000B',LTTOT_TOP_AMOUNT='75,000'),
            dict(MODEL_NO='3',HOUSE_TY='059.9000A',LTTOT_TOP_AMOUNT='50,000')]


def test_family_range_and_no_invented_area():
    result=family_price(empty_unit('84C'),models())
    assert result['sale_price_range_krw']=={'min':700000000,'max':750000000}
    assert result['sale_price_krw']==750000000
    assert result['area_sqm'] is None
    assert len(result['price_candidate_types'])==2


def test_missing_price_and_different_area_are_not_accepted():
    assert family_price(empty_unit('74'),models()) is None
    rows=models();rows[1]['LTTOT_TOP_AMOUNT']=None
    assert family_price(empty_unit('84'),rows) is None


def test_negative_range_and_failed_recalculation_clear_previous_range():
    unit,trades,target,locations,policy=analysis_inputs()
    unit=family_price(unit,models())
    result=calculate(unit,trades,target,locations,policy,NOW.date())
    assert result['estimated_gap_range_krw']=={'min':-50000000,'max':0}
    assert result['estimated_gap_krw']==-50000000
    assert result['confidence']=='low'
    assert 'type_unconfirmed' in result['analysis_reason']
    failed=calculate(result,[],target,locations,policy,NOW.date())
    assert failed['estimated_gap_range_krw'] is None
    assert failed['estimated_gap_krw'] is None


def test_pipeline_fallback_and_exact_match_precedence(monkeypatch):
    for key in ('KAKAO_REST_API_KEY','VWORLD_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    class Catalog:
        def discover(self,item):
            return ({'evidence_url':'https://www.gg.go.kr','official_address':item['address'],
                     'housing_manage_no':'1','pblanc_no':'2'}, {}, models())
    listing=notice()
    listing['units']=[dict(empty_unit('84C'),allocation_count=1),dict(empty_unit('84A'),allocation_count=1)]
    _,_,_,_,policy=analysis_inputs()
    enrich([listing],BrokenClient(),NOW,{'projects':{},'trade_locations':{}},policy,None,None,apply_client=Catalog())
    family,exact=listing['units']
    assert family['sale_price_krw']==750000000
    assert family['sale_price_basis']=='area_family_maximum'
    assert exact['sale_price_krw']==700000000
    assert exact['sale_price_basis']=='maximum_base_price'
    validate(dict(schema_version='1.0.0',generated_at=NOW.isoformat(),last_success_at=None,
                  data_status='partial',sources=[],listings=[listing]))
