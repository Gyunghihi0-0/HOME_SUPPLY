"""Read HWP 5 BodyText records using the published Hancom binary specification."""
from io import BytesIO
import struct
import zlib
import olefile
from scripts.http_client import SourceError

def read_text(content):
    with olefile.OleFileIO(BytesIO(content)) as ole:
        header=ole.openstream('FileHeader').read()
        if not header.startswith(b'HWP Document File') or len(header)<40:raise SourceError('unsupported_hwp_version')
        flags=struct.unpack_from('<I',header,36)[0]
        if flags & 6:raise SourceError('encrypted_or_distributed_hwp')
        chunks=[];total=0
        for path in sorted(ole.listdir()):
            if len(path)!=2 or path[0]!='BodyText' or not path[1].startswith('Section'):continue
            data=ole.openstream(path).read()
            if flags & 1:
                inflater=zlib.decompressobj(-15);data=inflater.decompress(data,20_000_001)
                if inflater.unconsumed_tail or len(data)>20_000_000:raise SourceError('expanded_document_too_large')
                if not inflater.eof:raise SourceError('invalid_hwp_compression')
            total+=len(data)
            if total>40_000_000:raise SourceError('expanded_document_too_large')
            offset=0
            while offset+4<=len(data):
                rec=struct.unpack_from('<I',data,offset)[0];offset+=4
                tag=rec & 1023;size=rec>>20
                if size==4095:
                    if offset+4>len(data):raise SourceError('invalid_hwp_record')
                    size=struct.unpack_from('<I',data,offset)[0];offset+=4
                if offset+size>len(data):raise SourceError('invalid_hwp_record')
                value=data[offset:offset+size];offset+=size
                if tag!=67:continue
                words=struct.unpack('<'+'H'*(len(value)//2),value[:len(value)//2*2])
                chars=[];i=0
                while i<len(words):
                    ch=words[i]
                    if ch in (9,10,13):chars.append(' ');i+=1
                    elif ch in (1,2,3,4,5,6,7,8,11,12,14,15,16,17,18,19,20,21,22,23):i+=8
                    elif ch<32:i+=1
                    else:chars.append(chr(ch));i+=1
                if chars:chunks.append(''.join(chars).encode('utf-16-le','surrogatepass').decode('utf-16-le',errors='replace'))
        return '\n'.join(chunks)
