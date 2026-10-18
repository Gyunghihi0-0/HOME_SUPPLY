"""Reproducible JSON Schema source; run only when changing the contract."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def obj(properties, required=None, **extra):
    return dict(type="object", properties=properties, required=required or list(properties), additionalProperties=False, **extra)

def enum(*values):
    return {"enum": list(values)}

def nullable(kind, **extra):
    return {"type": [kind, "null"], **extra}

def array(ref):
    return {"type": "array", "items": {"$ref": f"#/$defs/{ref}"}}

TEXT = nullable("string")
URL = nullable("string", format="uri", pattern="^https://")
STAMP = nullable("string", format="date-time", pattern=r'^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$')
DAY = nullable("string", format="date")
NUM = nullable("number")
MONEY = nullable("integer", minimum=0)
COUNT = nullable("integer", minimum=0)
TEMPORAL = {"oneOf": [{"type": "null"}, {"type": "string", "format": "date", "pattern": r'^\d{4}-\d{2}-\d{2}$'}, {"type": "string", "format": "date-time", "pattern": r'^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$'}]}

def schema():
    comparable = obj({"id": {"type":"string"}, "apartment_name": {"type":"string"}, "location": {"type":"string"},
        "area_sqm": {"type":"number", "exclusiveMinimum":0}, "trade_date": {"type":"string","format":"date"},
        "price_krw": {"type":"integer","exclusiveMinimum":0}, "build_year": nullable("integer",minimum=1900),
        "distance_m": nullable("number",minimum=0), "source_url": URL, "collected_at": STAMP})
    unit = obj({"type_id":{"type":"string"}, "area_sqm": nullable("number",exclusiveMinimum=0), "allocation_count":COUNT,
        "sale_price_krw":nullable("integer",exclusiveMinimum=0), "sale_price_basis":enum("maximum_base_price","exact_base_price","unknown","area_family_maximum"),
        "sale_price_evidence_url":URL, "comparison_median_krw":NUM, "estimated_gap_krw":NUM, "gap_rate_pct":NUM,
        "comparables_count":{"type":"integer","minimum":0}, "confidence":enum("high","medium","low","unavailable"),
        "analysis_reason":TEXT, "analysis_policy_version":TEXT, "comparables":array("comparable")})
    unit['properties'].update(sale_price_range_krw=obj({'min':MONEY,'max':MONEY}),
        price_candidate_types={'type':'array','items':{'type':'string'},'minItems':1,'uniqueItems':True},
        estimated_gap_range_krw={'anyOf':[{'type':'null'},obj({'min':NUM,'max':NUM})]})
    eligibility = obj({"yongin_status":enum("eligible","ineligible","unknown"),
        "disability_scope":enum("both","mild_only","severe_only","unknown"), "evidence_url":URL,
        "evidence_text":TEXT, "scoring_note":TEXT, "conditions":{"type":"array","items":{"type":"string"}},
        "rule_version":{"type":"string"}})
    listing = obj({"id":{"type":"string","pattern":"^[A-Za-z0-9_-]+$"}, "name":{"type":"string","minLength":1},
        "address":TEXT,"region":TEXT,"district":TEXT,"housing_type":enum("private_apt","public_apt","unknown"),
        "status":enum("open","upcoming","closed","cancelled","unknown"), "apply_start_at":TEMPORAL,"apply_end_at":TEMPORAL,
        "deadline_note":TEXT,"notice_url":URL,"notice_updated_at":TEMPORAL,"updated_at":STAMP,
        "eligibility":{"$ref":"#/$defs/eligibility"}, "units":array("unit"),
        "attachments":array("attachment"),"notice_history":array("notice_revision"),
        "housing_manage_no":TEXT,"pblanc_no":TEXT,"location_verified":{"type":"boolean"},
        "collection_issues":{"type":"array","items":{"type":"string"}}})
    source = obj({"id":{"type":"string"},"name":{"type":"string"},"url":URL,
        "status":enum("ok","partial","error","not_configured","not_checked"),"checked_at":STAMP,"last_success_at":STAMP,
        "error_code":TEXT,"message":TEXT,"records_count":COUNT})
    revision = obj({"notice_url":URL,"published_on":DAY,"content_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},
        "observed_at":STAMP,"change_type":enum("initial","changed","correction","cancellation")})
    attachment = obj({"url":URL,"name":{"type":"string"},"parse_status":enum("parsed","unsupported","error","not_checked"),"error_code":TEXT})
    top = obj({"schema_version":{"const":"1.0.0"},"generated_at":dict(STAMP,type='string'),"last_success_at":STAMP,
        "data_status":enum("ok","partial","stale","error"),"sources":array("source"),"listings":array("listing")})
    top.update({"$schema":"https://json-schema.org/draft/2020-12/schema", "$defs":dict(comparable=comparable,unit=unit,
        eligibility=eligibility,listing=listing,source=source,notice_revision=revision,attachment=attachment)})
    return top

if __name__ == "__main__":
    path=ROOT/'contracts/latest.schema.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(schema(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
