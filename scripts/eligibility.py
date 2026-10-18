import json
import re
from pathlib import Path

RULES=json.loads((Path(__file__).resolve().parents[1]/'config/eligibility.json').read_text(encoding='utf-8'))

def classify(text, url):
    result=dict(yongin_status='unknown',disability_scope='unknown',evidence_url=None,evidence_text=None,
        scoring_note='장애 정도 배점과 신청 제한은 별개이며 개인별 최종 자격을 보장하지 않습니다.',conditions=[],rule_version=RULES['version'])
    # Only labeled qualification line, never address, score table or general subscription dates.
    lines=[re.sub(r'\s+',' ',line).strip() for line in text.splitlines() if re.search(r'신청\s*자격\s*[:：]',line)]
    if len(lines)!=1:
        return result
    line=lines[0]
    result.update(evidence_url=url,evidence_text=line[:1000])
    if any(marker in line for marker in RULES['review_markers']):
        result['conditions']=['조건·예외에 대한 공식 안내 확인 필요']
        return result
    if any(re.search(p,line) for p in RULES['region_allow_patterns']):
        result['yongin_status']='eligible'
    if any(re.search(p,line) for p in RULES['severe_only_patterns']):
        result['disability_scope']='severe_only'
    elif any(re.search(p,line) for p in RULES['mild_only_patterns']):
        result['disability_scope']='mild_only'
    elif re.search(RULES['unrestricted_pattern'],line):
        result['disability_scope']='both'
    result['conditions']=[line.split(':',1)[-1].strip()]
    return result
