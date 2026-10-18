import json
import re
from pathlib import Path

RULES=json.loads((Path(__file__).resolve().parents[1]/'config/eligibility.json').read_text(encoding='utf-8'))

def classify(text, url):
    result=dict(yongin_status='unknown',disability_scope='unknown',evidence_url=None,evidence_text=None,
        scoring_note='장애 정도 배점과 신청 제한은 별개이며 개인별 최종 자격을 보장하지 않습니다.',conditions=[],rule_version=RULES['version'])
    # Only labeled qualification line, never address, score table or general subscription dates.
    label=r'신청\s*자격(?:\s*및\s*주택소유여부\s*확인대상자)?\s*[:：]'
    raw=text.splitlines();indices=[i for i,line in enumerate(raw) if re.search(label,line)]
    if len(indices)!=1:
        return result
    i=indices[0];parts=[raw[i]]
    for more in raw[i+1:i+7]:
        if re.match(r'\s*[○□■※]|\s*(?:신청기간|신청방법|선정방법|접수)',more):break
        if len(' '.join(parts))>500:break
        parts.append(more)
    line=re.sub(r'\s+',' ',' '.join(parts)).strip()
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
    elif re.search(RULES['unrestricted_pattern'],line) or ('무주택' in line and '장애인' in line and not re.search(r'중증|경증|심한|심하지',line)):
        result['disability_scope']='both'
    result['conditions']=[line.split(':',1)[-1].strip()]
    return result
