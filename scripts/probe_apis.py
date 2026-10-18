"""Authenticated read-only smoke test. Does not publish responses or secrets."""
from datetime import datetime
import os
from scripts.apis import Applyhome,Molit
from scripts.collector import KST
from scripts.http_client import Client,SourceError

def main():
    client=Client();now=datetime.now(KST);failed=False
    probes={
        'applyhome':lambda:Applyhome(client,os.getenv('APPLYHOME_SERVICE_KEY')).get('getAPTLttotPblancDetail',{'cond[RCRIT_PBLANC_DE::GTE]':now.date().replace(day=1).isoformat()}),
        'molit_detail_15126468':lambda:Molit(client,os.getenv('MOLIT_SERVICE_KEY')).month('41463',now.strftime('%Y%m'),now)
    }
    for name,probe in probes.items():
        try:print(f'{name}: ok, records={len(probe())}')
        except SourceError as exc:print(f'{name}: {exc}');failed=True
    return int(failed)

if __name__=='__main__':raise SystemExit(main())
