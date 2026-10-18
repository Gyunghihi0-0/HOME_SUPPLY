import json,os,tempfile

def write_report(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    body=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    fd,name=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:out.write(body)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
