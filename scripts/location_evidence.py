"""Public apartment-coordinate evidence for reproducible distance calculations."""
import json
import math
import os
import tempfile
from scripts.validate import CHECKER

def write_locations(path,data):
    if set(data)!={'schema_version','generated_at','targets','comparables'} or data['schema_version']!='1.0.0':raise ValueError('unexpected_location_document')
    CHECKER.check(data['generated_at'],'date-time')
    for group in ('targets','comparables'):
        for value in data[group].values():
            lat,lon=value['coordinates']
            if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (lat,lon)) or not(-90<=lat<=90 and -180<=lon<=180):raise ValueError('invalid_coordinates')
            CHECKER.check(value['evidence_url'],'uri');CHECKER.check(value['checked_at'],'date-time')
            from urllib.parse import urlsplit,parse_qs
            if any(k.lower() in ('key','apikey','api_key','servicekey','token') for k in parse_qs(urlsplit(value['evidence_url']).query)):raise ValueError('credential_in_evidence_url')
            if set(value)-{'address','coordinates','build_year','lawd_codes','evidence_url','checked_at','location','apartment_name'}:raise ValueError('unexpected_location_field')
    body=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if path.exists() and path.read_text(encoding='utf-8')==body:return
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as out:out.write(body)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
