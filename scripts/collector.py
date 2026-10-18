import hashlib
import re
import time
import os
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin
from bs4 import BeautifulSoup
from scripts.eligibility import classify
from scripts.http_client import SourceError
from scripts.documents import read_document
from scripts.structured import allocation_units,exclusive_areas

KST=timezone(timedelta(hours=9))
ORIGIN='https://www.gg.go.kr'
BOARD=ORIGIN+'/bbs/board.do?bsIdx=504&menuId=1878'
EXCLUDE=re.compile(r'선정자|대상자\s*명단|선정\s*결과|모바일|FAQ|카드뉴스|배점기준|중복신청|공지사항|접수기준\s*변경')

def body_text(body):
    fragment=BeautifulSoup(str(body),'html.parser')
    for br in fragment.select('br'):br.replace_with('\n')
    for block in fragment.select('p,li,tr'):block.append('\n')
    return '\n'.join(re.sub(r'\s+',' ',line).strip() for line in fragment.get_text(' ',strip=False).splitlines() if line.strip())

def attachment_has_eligibility_restriction(text):
    # Residence-duration score rows do not restrict eligibility. Only explicit
    # qualifying language is a reason to hold the body-level classification.
    return bool(re.search(r'(?:중증|경증)\s*장애인만|장애의\s*정도가\s*심(?:한|하지\s*않은)\s*장애인만|(?:신청\s*자격|신청\s*대상)[^\n]{0,100}(?:경기도|용인시|거주자)[^\n]{0,35}(?:제외|한정|이상\s*계속\s*거주)',text))

def parse_period(text,reference_date=None):
    line=next((x for x in text.splitlines() if re.search(r'신청\s*기간\s*[:：]',x)), '')
    # Refuse inferred years/months other than a right-hand month inherited from the explicit start date.
    pattern=r"[’'‘]?(?P<y>20\d{2}|\d{2})\s*[.년]\s*(?P<m>\d{1,2})\s*[.월]\s*(?P<d>\d{1,2})\s*[.일]?(?:\s*\([^)]*\))?(?:\s*(?P<h>\d{1,2}):(?P<mi>\d{2}))?"
    left,*right=re.split(r'[~∼～]',line,maxsplit=1)
    if reference_date and not re.search(pattern,left):
        short=re.search(r'[:：]\s*([.\d\s월일()가-힣:]+)$',left)
        if short:left=left[:short.start(1)]+str(date.fromisoformat(reference_date).year)+'.'+short[1]
    m=re.search(pattern,left)
    if not m or not right:return None,None
    y=int(m['y']); y=y+2000 if y<100 else y
    def render(year,month,day,hour,minute):
        d=date(year,int(month),int(day))
        return datetime(year,int(month),int(day),int(hour),int(minute),tzinfo=KST).isoformat() if hour else d.isoformat()
    try:
        start=render(y,m['m'],m['d'],m['h'],m['mi'])
        rhs=right[0].strip().lstrip('.')
        full=re.search(pattern,rhs)
        if full:
            ey=int(full['y']); ey=ey+2000 if ey<100 else ey
            end=render(ey,full['m'],full['d'],full['h'],full['mi'])
        else:
            e=re.match(r'(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[.일]?(?:\s*\([^)]*\))?(?:\s*(\d{1,2}):(\d{2}))?',rhs)
            if not e:return None,None
            end=render(y,*e.groups())
        if end<start:return None,None
        if reference_date and abs((date.fromisoformat(start[:10])-date.fromisoformat(reference_date)).days)>120:return None,None
        return start,end
    except ValueError:return None,None

def status_at(start,end,now,cancelled=False):
    if cancelled:return 'cancelled'
    if start and (now.date()<date.fromisoformat(start) if len(start)==10 else now<datetime.fromisoformat(start)):
        return 'upcoming'
    if end and (now.date()>date.fromisoformat(end) if len(end)==10 else now>datetime.fromisoformat(end)):
        return 'closed'
    # On a date-only deadline, exact open/closed is unknown.
    if end and len(end)==10 and now.date()==date.fromisoformat(end):return 'unknown'
    return 'open' if start and end else 'unknown'

def parse_notice(html,row,now):
    soup=BeautifulSoup(html,'html.parser'); body=soup.select_one('.s-v-board-default .k-content-padding')
    if body is None:raise SourceError('notice_structure_changed')
    text=body_text(body)
    title=BeautifulSoup(row['SUBJECT'],'html.parser').get_text().strip()
    name_match=re.search(r'[「“](.*?)[」”]',title)
    # Unquoted or multi-project notices retain full official title; never guess project identity.
    name=name_match[1] if name_match else title
    url=ORIGIN+'/bbs/boardView.do?'+urlencode(dict(bsIdx=504,menuId=1878,bIdx=row['B_IDX']))
    start,end=parse_period(text,row['WRITE_DATE2'])
    address_match=re.search(r'공급\s*위치\s*[:：]\s*([^\n]+)',text)
    address=address_match[1].strip() if address_match else None
    district_match=re.search(r'([가-힣]+구)\b',address or '')
    region_match=re.search(r'([가-힣]+(?:시|군))\b',address or '')
    attachments=[]
    for a in soup.select('.s-v-board-default a.filename[href]'):
        filename=re.sub(r'\s*\[[^]]+\]\s*$','',a.get_text(' ',strip=True))
        if EXCLUDE.search(filename):continue
        attachments.append(dict(url=urljoin(ORIGIN,a['href']),name=filename,parse_status='not_checked',error_code=None))
    listing=dict(id='gg_'+str(row['B_IDX']),name=name,address=address,region=region_match[1] if region_match else None,
        district=district_match[1] if district_match else None,housing_type='unknown',status=status_at(start,end,now,'취소' in title),
        apply_start_at=start,apply_end_at=end,deadline_note='정확한 마감 시각은 공식 안내 확인 필요' if end and len(end)==10 else None,
        notice_url=url,notice_updated_at=row['WRITE_DATE2'],updated_at=now.isoformat(),eligibility=classify(text,url),units=[],
        attachments=attachments,notice_history=[dict(notice_url=url,published_on=row['WRITE_DATE2'],
        content_sha256=hashlib.sha256((title+'\n'+text).encode()).hexdigest(),observed_at=now.isoformat(),
        change_type='cancellation' if '취소' in title else 'correction' if re.search('변경|정정',title) else 'initial')],
        housing_manage_no=None,pblanc_no=None,location_verified=False,collection_issues=[])
    if start and not re.search(r"[’'‘]?(?:20\d{2}|\d{2})\s*[.년]\s*\d{1,2}\s*[.월]\s*\d{1,2}",next((l for l in text.splitlines() if '신청' in l and '기간' in l),'')):
        listing['deadline_note']='연도는 공고 게시연도 기준으로 해석했습니다. 정확한 마감 시각은 공식 안내 확인 필요'
    if re.search(r'(?:관련|전체)\s*일정.{0,30}연기|(?:신청|접수)\s*(?:기간|일정).{0,30}(?:연기|미정)',text):
        listing['collection_issues'].append('application_schedule_postponed')
    elif re.search(r'선정자?\s*발표일.{0,30}연기',text):
        listing['collection_issues'].append('announcement_only_update')
    return listing

def collect(client,now,pages=3,attachments=True,start_page=0,target_names=None,previous=None,on_record=None,budget_seconds=None,page_order=None,attempted_at=None):
    deadline=time.monotonic()+budget_seconds if budget_seconds is not None else float('inf')
    previous=previous or []
    client.request(BOARD,robots=True)
    records={}; errors=[]; seen=set(); partial=False
    for page in page_order or range(start_page,start_page+pages):
        if time.monotonic()>=deadline:partial=True;errors.extend(['notice_budget_exhausted','notice_budget_exhausted_page_'+str(page)]);break
        url=ORIGIN+'/ajax/board/getList.do'
        import json
        raw=client.request(url,method='POST',data=dict(bsIdx='504',bcIdx='0',menuId='1878',offset=page*15,limit=15),robots=True)
        try:d=json.loads(raw)
        except ValueError:raise SourceError('board_invalid_json') from None
        if not isinstance(d.get('items'),list) or not isinstance(d.get('total'),int):raise SourceError('board_structure_changed')
        page_rows=sorted(d['items'],key=lambda row:(attempted_at or {}).get('gg_'+str(row.get('B_IDX')),'')) if attempted_at is not None else d['items']
        for row in page_rows:
            if time.monotonic()>=deadline:partial=True;errors.extend(['notice_budget_exhausted','notice_budget_exhausted_page_'+str(page)]);break
            if not all(k in row for k in ('B_IDX','SUBJECT','WRITE_DATE2')):raise SourceError('board_row_changed')
            if str(row['B_IDX']) in seen:continue
            seen.add(str(row['B_IDX']))
            title=BeautifulSoup(row['SUBJECT'],'html.parser').get_text()
            if '특별공급' not in title or EXCLUDE.search(title):continue
            if target_names:
                from scripts.matching import compact
                if not any(compact(name) in compact(title) for name in target_names):continue
                if (now.date()-date.fromisoformat(row['WRITE_DATE2'])).days>120:continue
            notice_url=ORIGIN+'/bbs/boardView.do?'+urlencode(dict(bsIdx=504,menuId=1878,bIdx=row['B_IDX']))
            try:
                item=parse_notice(client.request(notice_url,robots=True),row,now)
                reusable=[p for p in previous if '_p' not in p['id'] and p['notice_url']==item['notice_url']
                          and p['notice_history'][-1]['content_sha256']==item['notice_history'][-1]['content_sha256']
                          and {(a['url'],a['name']) for a in p['attachments']}=={(a['url'],a['name']) for a in item['attachments']}
                          and os.getenv('HOME_SUPPLY_FORCE_REFRESH','').lower()!='true'
                          and p.get('updated_at') and 0 <= (now-datetime.fromisoformat(p['updated_at'])).total_seconds() <= 3600
                          and p['attachments'] and all(a['parse_status']=='parsed' for a in p['attachments'])]
                if len(reusable)==1:
                    prior=reusable[0]
                    for key in ('attachments','units','eligibility'):item[key]=deepcopy(prior[key])
                    item['collection_issues']=sorted(set(prior['collection_issues']+['unchanged_attachment_evidence_reused']))
                    records[item['id']]=item
                    if on_record:on_record(item)
                    continue
                documents=[];unit_candidates=[];attachment_eligibility=[]
                if attachments:
                    for a in item['attachments']:
                        if time.monotonic()>=deadline:
                            partial=True;a['error_code']='attachment_stage_deferred'
                            item['collection_issues'].append('attachment_stage_deferred')
                            item['eligibility']['yongin_status']='unknown';item['eligibility']['disability_scope']='unknown'
                            continue
                        try:
                            document=read_document(client.request(a['url'],robots=True),a['name'])
                            extracted=document['text'];documents.append(extracted)
                            evidence=classify(extracted,a['url'])
                            if evidence['yongin_status']!='unknown':attachment_eligibility.append(evidence)
                            a['parse_status']='parsed'
                            item['collection_issues'].append('attachment_text_extracted')
                            try:
                                allocation=allocation_units(document['tables'],document.get('table_contexts'))
                                unit_candidates.extend(allocation)
                                if any(':' in u['type_id'] for u in allocation):item['collection_issues'].append('multi_project_notice_requires_block_match')
                            except ValueError:
                                item['collection_issues'].append('allocation_conflict_review_required')
                            if attachment_has_eligibility_restriction(extracted):
                                item['eligibility']['yongin_status']='unknown'
                                item['eligibility']['disability_scope']='unknown'
                                item['collection_issues'].append('attachment_eligibility_review_required')
                        except Exception as exc:
                            a['parse_status']='unsupported' if isinstance(exc,SourceError) and 'unsupported' in str(exc) else 'error'
                            a['error_code']=str(exc) if isinstance(exc,SourceError) else 'document_parse_error'
                            item['eligibility']['yongin_status']='unknown';item['eligibility']['disability_scope']='unknown'
                            partial=True
                records[item['id']]=item
                if unit_candidates:
                    by_type={};conflicts=set()
                    for unit in unit_candidates:
                        if unit['type_id'] in by_type and by_type[unit['type_id']]['allocation_count']!=unit['allocation_count']:conflicts.add(unit['type_id'])
                        by_type[unit['type_id']]=unit
                    item['units']=[u for key,u in by_type.items() if key not in conflicts]
                    for doc in documents:item['units']=exclusive_areas(doc,item['units'])
                    if conflicts:item['collection_issues'].append('allocation_conflict_review_required')
                if attachment_eligibility and 'attachment_eligibility_review_required' not in item['collection_issues']:
                    unique={(e['yongin_status'],e['disability_scope']) for e in attachment_eligibility}
                    if len(unique)==1:item['eligibility']=attachment_eligibility[0]
                item['collection_issues']=sorted(set(item['collection_issues']))
                if on_record:on_record(item)
            except Exception:
                errors.append('gg_'+str(row['B_IDX']));partial=True
        if page_order is None and (page+1)*15>=d['total']:break
    return list(records.values()),partial,errors
