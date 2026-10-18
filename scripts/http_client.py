"""Bounded requests. Never serialize request URLs containing credentials."""
import os
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class SourceError(RuntimeError):
    pass

class Client:
    def __init__(self, cache_dir='.cache', pause=1, timeout=(8,20), retries=2):
        self.timeout=timeout
        self.session=requests.Session()
        self.session.headers['User-Agent']='HomeSupplyResearch/1.0 (official public housing notices; daily)'
        self.session.mount('https://',HTTPAdapter(max_retries=Retry(total=retries,backoff_factor=1,status_forcelist=[429,500,502,503,504],allowed_methods=['GET','POST'],respect_retry_after_header=False,raise_on_status=False)))
        self.cache_dir=Path(cache_dir)
        self.pause=pause
        self.robots={}
        self.failed_origins={}
        self.deadline=None

    def request(self,url,method='GET',params=None,data=None,ttl=0,robots=False,headers=None,public_document=False):
        remaining=self.deadline-time.monotonic() if self.deadline else None
        if remaining is not None and remaining<=0:raise SourceError('notice_budget_exhausted')
        if os.getenv('HOME_SUPPLY_FORCE_REFRESH','').lower()=='true':ttl=0
        if urlsplit(url).scheme!='https':
            raise SourceError('insecure_url')
        if robots:
            self.check_robots(url)
        # Key contains no secret; API responses may be cached privately, not published.
        public_params={k:v for k,v in (params or {}).items() if k.lower() not in ('servicekey','key','apikey','api_key','token')}
        digest=hashlib.sha256(json.dumps([url,method,public_params,data],sort_keys=True).encode()).hexdigest()
        cache=self.cache_dir/(digest+'.bin')
        metadata=self.cache_dir/(digest+'.headers.json')
        request_headers=dict(headers or {})
        if public_document and cache.exists() and metadata.exists():
            try:
                validators=json.loads(metadata.read_text(encoding='utf-8'))
                if validators.get('etag'):request_headers['If-None-Match']=validators['etag']
                if validators.get('modified'):request_headers['If-Modified-Since']=validators['modified']
            except (ValueError,OSError):pass
        if ttl and cache.exists() and time.time()-cache.stat().st_mtime<ttl:
            return cache.read_bytes()
        parts=urlsplit(url)
        origin=(parts.scheme,parts.netloc)
        if origin in self.failed_origins:
            raise SourceError(self.failed_origins[origin])
        try:
            time.sleep(self.pause)
            timeout=self.timeout if remaining is None else tuple(max(.1,min(v,remaining)) for v in self.timeout)
            with self.session.request(method,url,params=params,data=data,headers=request_headers,timeout=timeout,stream=True,allow_redirects=False) as response:
                if response.status_code==304 and public_document and cache.exists():return cache.read_bytes()
                if response.status_code!=200:
                    if response.status_code==429 or response.status_code>=500:
                        self.failed_origins[origin]=f'http_{response.status_code}'
                    raise SourceError(f'http_{response.status_code}')
                chunks=[]; size=0
                for chunk in response.iter_content(65536):
                    if self.deadline and time.monotonic()>=self.deadline:raise SourceError('notice_budget_exhausted')
                    size+=len(chunk)
                    if size>20_000_000:
                        raise SourceError('response_too_large')
                    chunks.append(chunk)
                content=b''.join(chunks)
                if public_document:
                    cache.parent.mkdir(parents=True,exist_ok=True)
                    cache.write_bytes(content)
                    metadata.write_text(json.dumps({'etag':response.headers.get('ETag'),'modified':response.headers.get('Last-Modified')}),encoding='utf-8')
        except requests.RequestException:
            # Retries have already been exhausted. Stop repeating a host outage
            # for every listing; another source and the next daily run still proceed.
            self.failed_origins[origin]='network_error'
            raise SourceError('network_error') from None
        if ttl:
            # Many public gateways return authentication/quota failures with HTTP 200.
            # Never cache those failures after the user repairs a key or quota.
            if content.lstrip().startswith(b'{'):
                try:payload=json.loads(content)
                except ValueError:raise SourceError('invalid_json_response') from None
                odcloud=isinstance(payload.get('data'),list) and 'totalCount' in payload
                vworld=isinstance(payload.get('response'),dict) and payload['response'].get('status')=='OK'
                if isinstance(payload.get('response'),dict) and payload['response'].get('status')=='ERROR':
                    code=str(payload['response'].get('error',{}).get('code','UNKNOWN'))
                    raise SourceError('vworld_api_'+code if re.fullmatch(r'[A-Z_]{1,60}',code) else 'vworld_api_UNKNOWN')
                if not (odcloud or vworld):
                    raise SourceError('api_application_error')
            else:
                from defusedxml import ElementTree as ET
                try:root=ET.fromstring(content)
                except Exception:raise SourceError('invalid_xml_response') from None
                if root.findtext('.//resultCode') not in ('000','00'):
                    raise SourceError('api_application_error')
            cache.parent.mkdir(parents=True,exist_ok=True)
            cache.write_bytes(content)
        return content

    def check_robots(self,url):
        parts=urlsplit(url); origin=f'{parts.scheme}://{parts.netloc}'
        if origin not in self.robots:
            body=self.request(origin+'/robots.txt').decode('utf-8')
            # Honor wildcard UA group including * and $ path patterns.
            rules=[]; active=False
            for line in body.splitlines():
                line=line.split('#',1)[0].strip()
                if ':' not in line: continue
                key,value=[v.strip() for v in line.split(':',1)]
                if key.lower()=='user-agent': active=value=='*'
                elif active and key.lower() in ('allow','disallow') and value:
                    rules.append((value,key.lower()=='allow'))
            self.robots[origin]=rules
        matches=[]
        for rule,allow in self.robots[origin]:
            anchored=rule.endswith('$'); pattern=re.escape(rule.rstrip('$')).replace(r'\*','.*')
            if re.match('^'+pattern+('$' if anchored else ''),parts.path): matches.append((len(rule.replace('*','')),allow))
        if matches and not max(matches)[1]:
            raise SourceError('robots_disallowed')
