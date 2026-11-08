"""Validated collection evidence, separate from project/analysis completeness."""
from functools import wraps
from contextlib import nullcontext
from datetime import datetime

def latest(stamps):return max(filter(None,stamps),key=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')))

def record_success(client,provider):
    audit=getattr(client,'collection_audit',None)
    meta=getattr(client,'response_meta',None)
    stamp=getattr(meta,'observed_at',None)
    if audit is None or not stamp:return
    with getattr(client,'collection_lock',nullcontext()):
        entry=audit.setdefault(provider,dict(live=0,cached=0,failures=0,last_success_at=None))
        entry['cached' if getattr(meta,'cached',False) else 'live']+=1
        entry['last_success_at']=latest([entry['last_success_at'],stamp])

def record_failure(client,provider):
    audit=getattr(client,'collection_audit',None)
    if audit is None:return
    with getattr(client,'collection_lock',nullcontext()):
        entry=audit.setdefault(provider,dict(live=0,cached=0,failures=0,last_success_at=None))
        entry['failures']+=1

def observe_failure(provider):
    def decorate(fn):
        @wraps(fn)
        def wrapped(first,*args,**kwargs):
            try:return fn(first,*args,**kwargs)
            except Exception as exc:
                if 'budget_exhausted' not in str(exc):record_failure(getattr(first,'client',first),provider)
                raise
        return wrapped
    return decorate

def attach_health(entry,client,previous=None):
    evidence=getattr(client,'collection_audit',{}).get(entry['id'],{})
    live=evidence.get('live',0);cached=evidence.get('cached',0);errors=evidence.get('failures',0)
    state='partial' if (live or cached) and errors else 'error' if errors else 'ok' if live else 'cached' if cached else 'not_checked'
    if entry['status']=='not_configured':state='not_configured'
    elif entry['status']=='error' and not errors:state='partial' if live or cached else 'error'
    stamps=list(filter(None,[(previous or {}).get('last_collected_at'),evidence.get('last_success_at')]))
    entry.update(collection_status=state,last_collected_at=latest(stamps) if stamps else None,
                 collection_responses=live,collection_cached_responses=cached,collection_errors=errors)
    return entry
