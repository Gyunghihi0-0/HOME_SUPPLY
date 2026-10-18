"""Re-extract selected official attachments without replacing notice periods."""
import argparse
from datetime import datetime
from pathlib import Path
from scripts.collector import KST,attachment_has_eligibility_restriction
from scripts.documents import read_document
from scripts.eligibility import classify
from scripts.http_client import Client
from scripts.pipeline import load,atomic_write
from scripts.structured import allocation_units,exclusive_areas

def recheck(input_path,output_path,ids):
    data=load(input_path);client=Client();now=datetime.now(KST)
    for listing in data['listings']:
        if listing['id'] not in ids:continue
        units=[];documents=[];evidence=[];restricted=False
        for attachment in listing['attachments']:
            try:
                doc=read_document(client.request(attachment['url'],robots=True),attachment['name'])
                documents.append(doc['text']);attachment.update(parse_status='parsed',error_code=None)
                result=classify(doc['text'],attachment['url'])
                if result['yongin_status']!='unknown':evidence.append(result)
                restricted=restricted or attachment_has_eligibility_restriction(doc['text'])
                try:units.extend(allocation_units(doc['tables'],doc['table_contexts']))
                except ValueError:listing['collection_issues'].append('allocation_conflict_review_required')
            except Exception:
                attachment.update(parse_status='error',error_code='document_recheck_failed')
        if units:
            listing['units']=units
            for text in documents:listing['units']=exclusive_areas(text,listing['units'])
            if any(':' in u['type_id'] for u in units):listing['collection_issues'].append('multi_project_notice_requires_block_match')
        if evidence and not restricted and len({(e['yongin_status'],e['disability_scope']) for e in evidence})==1:
            listing['eligibility']=evidence[0]
        listing['collection_issues']=sorted(set(listing['collection_issues']));listing['updated_at']=now.isoformat()
    data['generated_at']=now.isoformat();atomic_write(output_path,data)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--id',action='append',required=True)
    args=p.parse_args();recheck(args.input,args.output,set(args.id))
