import calendar
import math
from datetime import date
from statistics import median

def months_before(day,months):
    index=day.year*12+day.month-1-months
    year,month=divmod(index,12);month+=1
    return date(year,month,min(day.day,calendar.monthrange(year,month)[1]))

def distance(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,[a[0],a[1],b[0],b[1]])
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))

def calculate(unit,trades,target,locations,policy,today):
    result=dict(unit)
    result.update(comparison_median_krw=None,estimated_gap_krw=None,gap_rate_pct=None,comparables_count=0,
        comparables=[],confidence='unavailable',analysis_policy_version=policy['version'])
    if not policy['approved']:
        result['analysis_reason']='policy_pending';return result
    if not unit['sale_price_krw'] or not unit['area_sqm'] or not target or not target.get('coordinates') or not target.get('build_year') or not target.get('evidence_url'):
        result['analysis_reason']='price_area_or_verified_location_missing';return result
    candidates={}
    for trade in trades:
        loc=locations.get(trade['location']+'|'+trade['apartment_name'])
        if not loc or not loc.get('evidence_url') or not loc.get('coordinates'):continue
        day=date.fromisoformat(trade['trade_date'])
        if not months_before(today,policy['maximum_months'])<=day<=today:continue
        if abs(trade['area_sqm']/unit['area_sqm']-1)*100>policy['area_tolerance_pct']:continue
        if trade['build_year'] is None or abs(trade['build_year']-target['build_year'])>policy['build_year_tolerance']:continue
        dist=distance(target['coordinates'],loc['coordinates'])
        if dist>policy['radius_m']:continue
        candidates[trade['id']]=dict(trade,distance_m=round(dist,1))
    values=list(candidates.values())
    recent=[t for t in values if date.fromisoformat(t['trade_date'])>=months_before(today,policy['preferred_months'])]
    chosen=recent if len(recent)>=policy['minimum_trades'] else values
    if len(chosen)<policy['minimum_trades']:
        result['analysis_reason']='fewer_than_three_verified_trades';return result
    # Conservative hold on extreme spread; do not silently remove legitimate expensive/cheap trades.
    prices=[t['price_krw'] for t in chosen]; mid=median(prices)
    if min(prices)<=0 or max(abs(p-mid)/mid for p in prices)>0.5:
        result['analysis_reason']='outlier_review_required';return result
    gap=mid-unit['sale_price_krw']
    high=len(chosen)>=10 and len(recent)==len(chosen) and all(t['distance_m']<=1000 and abs(t['area_sqm']/unit['area_sqm']-1)<=0.05 and abs(t['build_year']-target['build_year'])<=5 for t in chosen)
    result.update(comparison_median_krw=mid,estimated_gap_krw=gap,gap_rate_pct=round(gap/unit['sale_price_krw']*100,2),
        comparables_count=len(chosen),comparables=sorted(chosen,key=lambda t:(t['trade_date'],t['id'])),
        confidence='high' if high else 'medium' if len(recent)>=3 and len(chosen)>=5 else 'low',analysis_reason='six_month_window' if chosen is recent else 'extended_to_twelve_months')
    return result
