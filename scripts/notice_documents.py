"""Content-addressed public attachment parsing with a per-document process limit."""
import hashlib,json,subprocess,sys
from pathlib import Path
from scripts.http_client import SourceError

def read_cached(content,name,cache_dir,timeout=8):
    key=hashlib.sha256(b'notice-parser-v1\0'+Path(name).suffix.lower().encode()+content).hexdigest()
    path=Path(cache_dir)/'notice-documents'/(key+'.json')
    if path.exists():
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    try:
        result=subprocess.run([sys.executable,'-m','scripts.notice_documents',name],input=content,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(.1,timeout),check=False)
    except subprocess.TimeoutExpired:raise SourceError('document_parse_timeout') from None
    if result.returncode:raise SourceError('document_parse_failed')
    document=json.loads(result.stdout)
    if document.get('error'):raise SourceError(document['error'])
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    return document

if __name__=='__main__':
    from scripts.documents import read_document
    try:document=read_document(sys.stdin.buffer.read(),sys.argv[1])
    except SourceError as exc:document={'error':str(exc)}
    except Exception:document={'error':'document_parse_failed'}
    sys.stdout.buffer.write(json.dumps(document,ensure_ascii=False).encode('utf-8'))
