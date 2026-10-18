"""Bounded requests. Never serialize request URLs containing credentials."""
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
    def __init__(self, cache_dir='.cache', pause=1):
        self.session=requests.Session()
        self.session.headers['User-Agent']='HomeSupplyResearch/1.0 (official public housing notices; daily)'
        self.session.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=1,status_forcelist=[429,500,502,503,504],allowed_methods=['GET','POST'],respect_retry_after_header=False)))
        self.cache_dir=Path(cache_dir)
        self.pause=pause
        self.robots={}

    def request(self,url,method='GET',params=None,data=None,ttl=0,robots=False):
        if urlsplit(url).scheme!='https':
            raise SourceError('insecure_url')
        if robots:
            self.check_robots(url)
        # Key contains no secret; API responses may be cached privately, not published.
        public_params={k:v for k,v in (params or {}).items() if k.lower()!='servicekey'}
        digest=hashlib.sha256(json.dumps([url,method,public_params,data],sort_keys=True).encode()).hexdigest()
        cache=self.cache_dir/(digest+'.bin')
        if ttl and cache.exists() and time.time()-cache.stat().st_mtime<ttl:
            return cache.read_bytes()
        try:
            time.sleep(self.pause)
            with self.session.request(method,url,params=params,data=data,timeout=(10,45),stream=True,allow_redirects=False) as response:
                if response.status_code!=200:
                    raise SourceError(f'http_{response.status_code}')
                chunks=[]; size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>20_000_000:
                        raise SourceError('response_too_large')
                    chunks.append(chunk)
                content=b''.join(chunks)
        except requests.RequestException:
            raise SourceError('network_error') from None
        if ttl:
            # Many public gateways return authentication/quota failures with HTTP 200.
            # Never cache those failures after the user repairs a key or quota.
            if content.lstrip().startswith(b'{'):
                try:payload=json.loads(content)
                except ValueError:raise SourceError('invalid_json_response') from None
                if not isinstance(payload.get('data'),list) or 'totalCount' not in payload:
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
