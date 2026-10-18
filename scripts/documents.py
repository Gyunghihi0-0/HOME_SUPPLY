"""Read public notices in memory; raw documents never enter docs/data."""
from io import BytesIO
import re
from zipfile import ZipFile
from defusedxml import ElementTree as ET
from pypdf import PdfReader
from scripts.http_client import SourceError

def read_document(content, name):
    tables=[];table_contexts=[]
    if name.lower().endswith('.hwpx'):
        with ZipFile(BytesIO(content)) as z:
            if sum(x.file_size for x in z.infolist())>40_000_000:
                raise SourceError('expanded_document_too_large')
            texts=[]
            for path in sorted(z.namelist()):
                if path.startswith('Contents/section') and path.endswith('.xml'):
                    root=ET.fromstring(z.read(path))
                    # Preserve paragraph boundaries; a run is not a paragraph.
                    for para in root.iter():
                        if para.tag.endswith('}p'):
                            if any(e.tag.endswith('}tbl') for e in para.iter()):continue
                            value=''.join(e.text for e in para.iter() if e.tag.endswith('}t') and e.text)
                            if value:texts.append(value)
                    context=None
                    for table in root.iter():
                        if table.tag.endswith('}p') and not any(e.tag.endswith('}tbl') for e in table.iter()):
                            paragraph=''.join(e.text for e in table.iter() if e.tag.endswith('}t') and e.text)
                            heading=re.match(r'^\s*[가-하]\.\s*[「“]([^」”]+)[」”]',paragraph)
                            if heading:context=heading[1].strip()
                        if not table.tag.endswith('}tbl'):continue
                        rows=[]
                        for tr in table:
                            if tr.tag.endswith('}tr'):
                                rows.append([' '.join(e.text for e in tc.iter() if e.tag.endswith('}t') and e.text) for tc in tr if tc.tag.endswith('}tc')])
                        if rows:tables.append(rows);table_contexts.append(context)
            text='\n'.join(texts)
    elif name.lower().endswith('.pdf'):
        reader=PdfReader(BytesIO(content))
        if reader.is_encrypted or len(reader.pages)>100:
            raise SourceError('pdf_not_supported')
        text='\n'.join(p.extract_text() or '' for p in reader.pages)
    elif name.lower().endswith('.hwp'):
        from scripts.hwp import read_text
        text=read_text(content)
    else:
        raise SourceError('unsupported_hwp_or_document')
    if len(text.strip())<20:
        raise SourceError('document_text_missing')
    return dict(text=text,tables=tables,table_contexts=table_contexts)

def extract(content,name):
    return read_document(content,name)['text']
