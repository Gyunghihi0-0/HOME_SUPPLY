import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin
from bs4 import BeautifulSoup
from scripts.eligibility import classify
from scripts.http_client import SourceError
from scripts.documents import extract

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
    return bool(re.search(r'(?:중증|경증)\s*장애인만|장애의\s*정도가\s*심(?:한|하지\s*않은)\s*장애인만|신청\s*(?:자격|대상|제한)[^\n]{0,160}(?:제외|한정|이상\s*계속\s*거주)',text))

def parse_period(text):
    line=next((x for x in text.splitlines() if re.search(r'신청\s*기간\s*[:：]',x)), '')
    # Refuse inferred years/months other than a right-hand month inherited from the explicit start date.
    pattern=r"[’'‘]?(?P<y>20\d{2}|\d{2})\s*[.년]\s*(?P<m>\d{1,2})\s*[.월]\s*(?P<d>\d{1,2})\s*[.일]?(?:\s*\([^)]*\))?(?:\s*(?P<h>\d{1,2}):(?P<mi>\d{2}))?"
    left,*right=re.split(r'[~∼～]',line,maxsplit=1)
    m=re.search(pattern,left)
    if not m or not right:return None,None
    y=int(m['y']); y=y+2000 if y<100 else y
    def render(year,month,day,hour,minute):
        d=date(year,int(month),int(day))
        return datetime(year,int(month),int(day),int(hour),int(minute),tzinfo=KST).isoformat() if hour else d.isoformat()
    try:
        start=render(y,m['m'],m['d'],m['h'],m['mi'])
        rhs=right[0].strip()
        full=re.search(pattern,rhs)
        if full:
            ey=int(full['y']); ey=ey+2000 if ey<100 else ey
            end=render(ey,full['m'],full['d'],full['h'],full['mi'])
        else:
            e=re.match(r'(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[.일]?(?:\s*\([^)]*\))?(?:\s*(\d{1,2}):(\d{2}))?',rhs)
            if not e:return None,None
            end=render(y,*e.groups())
        if end<start:return None,None
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
    start,end=parse_period(text)
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
    return listing

def collect(client,now,pages=3,attachments=True):
    client.request(BOARD,robots=True)
    records={}; errors=[]; seen=set(); partial=False
    for page in range(pages):
        url=ORIGIN+'/ajax/board/getList.do'
        import json
        raw=client.request(url,method='POST',data=dict(bsIdx='504',bcIdx='0',menuId='1878',offset=page*15,limit=15),robots=True)
        try:d=json.loads(raw)
        except ValueError:raise SourceError('board_invalid_json') from None
        if not isinstance(d.get('items'),list) or not isinstance(d.get('total'),int):raise SourceError('board_structure_changed')
        for row in d['items']:
            if not all(k in row for k in ('B_IDX','SUBJECT','WRITE_DATE2')):raise SourceError('board_row_changed')
            if str(row['B_IDX']) in seen:continue
            seen.add(str(row['B_IDX']))
            title=BeautifulSoup(row['SUBJECT'],'html.parser').get_text()
            if '특별공급' not in title or EXCLUDE.search(title):continue
            notice_url=ORIGIN+'/bbs/boardView.do?'+urlencode(dict(bsIdx=504,menuId=1878,bIdx=row['B_IDX']))
            try:
                item=parse_notice(client.request(notice_url,robots=True),row,now)
                if attachments:
                    for a in item['attachments']:
                        try:
                            extracted=extract(client.request(a['url'],robots=True),a['name'])
                            # Extraction is checked, but tables/extra restrictions need reviewed structured mapping.
                            a['parse_status']='parsed'
                            item['collection_issues'].append('attachment_structured_review_required')
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
            except Exception:
                errors.append('gg_'+str(row['B_IDX']));partial=True
        if (page+1)*15>=d['total']:break
    return list(records.values()),partial,errors
