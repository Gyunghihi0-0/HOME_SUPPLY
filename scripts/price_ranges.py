"""Area-family fallback only after the project identity has been verified."""
from scripts.apis import won, APPLY_SOURCE
from scripts.structured import normalize_type


def family_price(unit, models):
    kind = normalize_type(unit['type_id'])
    if not kind:
        return None
    candidates = [m for m in models if normalize_type(m.get('HOUSE_TY', ''))
                  and normalize_type(m['HOUSE_TY'])[0] == kind[0]]
    if not candidates:
        return None
    prices = [won(m.get('LTTOT_TOP_AMOUNT')) for m in candidates]
    # An incomplete family cannot establish its maximum or its full range.
    if any(p is None for p in prices):
        return None
    result = dict(unit)
    result.update(sale_price_krw=max(prices), sale_price_basis='area_family_maximum',
                  sale_price_evidence_url=APPLY_SOURCE,
                  sale_price_range_krw={'min': min(prices), 'max': max(prices)},
                  price_candidate_types=sorted(set(m['HOUSE_TY'] for m in candidates)),
                  estimated_gap_range_krw=None, comparison_median_krw=None,
                  estimated_gap_krw=None, gap_rate_pct=None, comparables=[],
                  comparables_count=0, confidence='unavailable',
                  analysis_reason='area_family_type_unconfirmed')
    # Never invent an exact exclusive area from the integer type label.
    return result
