import json
import sys
import re
from pathlib import Path
from datetime import datetime, timedelta
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
CHECKER=FormatChecker()

@CHECKER.checks('date-time',raises=ValueError)
def check_timestamp(value):
    if not isinstance(value,str):return True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',value):return False
    return datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is not None

@CHECKER.checks('uri')
def check_uri(value):
    if not isinstance(value,str):return True
    from urllib.parse import urlsplit
    parts=urlsplit(value)
    return parts.scheme=='https' and bool(parts.hostname) and not parts.username and not parts.password

def validate(data):
    schema=json.loads((ROOT/'contracts/latest.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema,format_checker=CHECKER).validate(data)
    ids=[x['id'] for x in data['listings']]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate listing IDs')
    for listing in data['listings']:
        e=listing['eligibility']
        if (e['yongin_status']!='unknown' or e['disability_scope']!='unknown') and not (e['evidence_url'] and e['evidence_text']):
            raise ValueError('eligibility requires evidence')
        for u in listing['units']:
            if u['comparables_count']!=len(u['comparables']):
                raise ValueError('comparable count mismatch')
            metrics=[u[k] for k in ['comparison_median_krw','estimated_gap_krw','gap_rate_pct']]
            if u['confidence']=='unavailable' and any(x is not None for x in metrics):
                raise ValueError('unavailable analysis must be null')
            if u['confidence']!='unavailable':
                if not u['allocation_count'] or u['allocation_count']<1:raise ValueError('analysis requires verified disability allocation')
                if not listing['location_verified'] or not u['sale_price_krw'] or len(u['comparables'])<3 or any(x is None for x in metrics):
                    raise ValueError('insufficient analysis evidence')
                from statistics import median
                price=median(c['price_krw'] for c in u['comparables'])
                gap=price-u['sale_price_krw']
                if price!=u['comparison_median_krw'] or gap!=u['estimated_gap_krw'] or round(gap/u['sale_price_krw']*100,2)!=u['gap_rate_pct']:
                    raise ValueError('analysis formula mismatch')

def freshness(data, now):
    stamp=data['last_success_at']
    return bool(stamp and timedelta(0)<=now-datetime.fromisoformat(stamp)<=timedelta(hours=36))

if __name__=='__main__':
    for arg in sys.argv[1:] or ['docs/data/latest.json']:
        validate(json.loads(Path(arg).read_text(encoding='utf-8')))
        print(f'VALID: {arg}')
