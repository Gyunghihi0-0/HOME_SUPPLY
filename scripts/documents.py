"""Read public notices in memory; raw documents never enter docs/data."""
from io import BytesIO
from zipfile import ZipFile
from defusedxml import ElementTree as ET
from pypdf import PdfReader
from scripts.http_client import SourceError

def extract(content, name):
    if name.lower().endswith('.hwpx'):
        with ZipFile(BytesIO(content)) as z:
            if sum(x.file_size for x in z.infolist())>40_000_000:
                raise SourceError('expanded_document_too_large')
            texts=[]
            for path in sorted(z.namelist()):
                if path.startswith('Contents/section') and path.endswith('.xml'):
                    root=ET.fromstring(z.read(path))
                    texts.extend(e.text for e in root.iter() if e.tag.endswith('}t') and e.text)
            text='\n'.join(texts)
    elif name.lower().endswith('.pdf'):
        reader=PdfReader(BytesIO(content))
        if reader.is_encrypted or len(reader.pages)>100:
            raise SourceError('pdf_not_supported')
        text='\n'.join(p.extract_text() or '' for p in reader.pages)
    else:
        raise SourceError('unsupported_hwp_or_document')
    if len(text.strip())<20:
        raise SourceError('document_text_missing')
    return text
