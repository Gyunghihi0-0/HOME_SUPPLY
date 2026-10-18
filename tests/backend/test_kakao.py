import json
import pytest
from scripts.kakao import Kakao
from scripts.http_client import SourceError

def document(parcel='212-3'):
    return dict(x='127.32',y='37.54',address=dict(address_name='경기 양평군 양서면 용담리 '+parcel,
        b_code='4183033021',region_1depth_name='경기',region_2depth_name='양평군'))

def test_exact_parcel_and_header_only_authentication():
    class Client:
        def request(self,url,**kw):
            assert kw['headers']=={'Authorization':'KakaoAK test-key'}
            assert 'key' not in kw['params'] and kw['ttl']==0
            return json.dumps({'documents':[document()]})
    geo=Kakao(Client(),'test-key')
    result=geo.locate('경기도 양평군 양서면 용담리 212-3번지 일원')
    assert result['lawd_codes']==['41830']
    assert result['coordinates']==[37.54,127.32]
    with pytest.raises(SourceError,match='exact_address_not_found'):
        geo.locate('경기도 양평군 양서면 용담리 212-4')

def test_ambiguous_result_and_block_not_promoted_to_verified_location():
    class Client:
        def request(self,*a,**kw):return json.dumps({'documents':[document(),document()]})
    with pytest.raises(SourceError,match='not_unique'):
        Kakao(Client(),'test-key').locate('경기도 양평군 양서면 용담리 212-3')
    with pytest.raises(SourceError,match='exact_address_not_found'):
        Kakao(Client(),'test-key').locate('경기도 광명시 구름산지구 A6블록')

def test_district_sampling_is_never_called_complete():
    class Client:
        def request(self,*a,**kw):return json.dumps({'documents':[
            dict(region_type='B',code='4183033021',region_1depth_name='경기',region_2depth_name='양평군')]})
    geo=Kakao(Client(),'test-key')
    assert geo.districts([37.54,127.32],2000)=={'41830':'경기 양평군'}
    assert geo.coverage_complete is False

def test_enrichment_computes_gap_from_verified_kakao_and_trade_rows(monkeypatch):
    from pathlib import Path
    from scripts import pipeline
    from scripts.apis import empty_unit, TRADE_SOURCE
    from scripts.replay_catalog import CapturedApplyhome
    from tests.backend.test_enrichment import sample_notice, NOW
    root=Path(__file__).resolve().parents[2]
    captured=json.loads((root/'tests/backend/fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))
    policy=json.loads((root/'config/analysis.json').read_text(encoding='utf-8'))
    item=sample_notice()
    item.update(name='쌍용 더 플래티넘 한강',address='경기도 양평군 양서면 용담리 212-3번지 일원')
    item['units']=[dict(empty_unit('84A',84.9947),allocation_count=1)]
    monkeypatch.setenv('KAKAO_REST_API_KEY','test-key')
    class Trades:
        fallback_used=False
        def __init__(self,*args,**kw):pass
        def month(self,lawd,month,now):
            if month!='202609':return []
            return [dict(id=str(i),location='41830|양서면 용담리|212-3',apartment_name='검증 표본',
                area_sqm=84.9,trade_date=f'2026-09-{10+i}',price_krw=price,build_year=2024,
                distance_m=None,source_url=TRADE_SOURCE,collected_at=now.isoformat())
                for i,price in enumerate([590000000,600000000,610000000])]
    monkeypatch.setattr(pipeline,'Molit',Trades)
    class Client:
        def request(self,url,**kw):
            if 'coord2regioncode' in url:
                return json.dumps({'documents':[dict(region_type='B',code='4183033021',region_1depth_name='경기',region_2depth_name='양평군')]})
            return json.dumps({'documents':[document()]})
    pipeline.enrich([item],Client(),NOW,dict(projects={},trade_locations={}),policy,None,'trade-test-key',apply_client=CapturedApplyhome(captured))
    unit=item['units'][0]
    assert unit['comparables_count']==3 and unit['comparison_median_krw']==600000000
    assert unit['estimated_gap_krw']==-148000000 and unit['gap_rate_pct']==-19.79
    assert unit['confidence']=='low' and '전체 지역 포괄 여부 미확인' in unit['analysis_reason']
