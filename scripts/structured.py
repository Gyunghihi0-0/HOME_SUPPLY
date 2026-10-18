"""Conservative extraction of official housing tables, never personal forms."""
import re
from scripts.apis import empty_unit

def normalize_type(value):
    value=re.sub(r'\s+','',value).upper().replace('㎡','').replace('M2','')
    m=re.fullmatch(r'0*(\d{2,3})(?:\.(\d+))?([A-Z][A-Z0-9-]*)?',value)
    return (int(m[1]),m[3] or '') if m else None

def allocation_units(tables,contexts=None):
    result={}
    contexts=contexts or [None]*len(tables)
    allocation_contexts={context for rows,context in zip(tables,contexts) if rows and context and any('배정' in c for c in rows[0])}
    multi=len(allocation_contexts)>1
    for rows,context in zip(tables,contexts):
        if not rows:continue
        header=[re.sub(r'\s+','',c) for c in rows[0]]
        typecol=next((i for i,c in enumerate(header) if c in ('신청형','주택형','타입')),None)
        countcol=next((i for i,c in enumerate(header) if c in ('배정세대','배정세대수')),None)
        # Only the disability recommendation's allocation table, not the all-institution total.
        if typecol is None or countcol is None:continue
        for row in rows[1:]:
            if max(typecol,countcol)>=len(row):continue
            label=re.sub(r'\s+','',row[typecol]).upper()
            if not normalize_type(label) or not re.fullmatch(r'\d+',row[countcol].strip()):continue
            if multi:
                if not context:raise ValueError('allocation_block_context_missing')
                label=context+':'+label
            count=int(row[countcol].strip())
            if count==0:continue
            if label in result and result[label]['allocation_count']!=count:
                raise ValueError('conflicting_disability_allocations')
            unit=empty_unit(label);unit['allocation_count']=count
            unit['analysis_reason']='sale_price_and_exclusive_area_pending'
            result[label]=unit
    return list(result.values())

def exclusive_areas(text, units):
    # Require an explicit exclusive-area heading and a unique type/decimal pair.
    if not re.search(r'전용\s*면적|주거\s*전용',text):return units
    candidates={}
    for line in text.splitlines():
        # Standard official table notation: 84A 84.9876 ...
        for m in re.finditer(r'(?<![\dA-Z])(\d{2,3}[A-Z])\s+(\d{2,3}\.\d{2,6})(?:\s|㎡|$)',line):
            if normalize_type(m[1])[0]==int(float(m[2])):
                candidates.setdefault(m[1],set()).add(float(m[2]))
    result=[]
    for unit in units:
        values=candidates.get(unit['type_id'],set())
        result.append(dict(unit,area_sqm=next(iter(values))) if len(values)==1 else unit)
    return result
