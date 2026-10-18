"""Reviewed official block geometry/parcel evidence; no project-name geocoding."""
import math,re
from urllib.parse import urlsplit
from scripts.http_client import SourceError
from scripts.matching import blocks


def resolve_block_location(item,geo,records):
    record=records.get(item['id'])
    if not record:raise SourceError('official_block_geometry_missing')
    url=record.get('evidence_url','');host=urlsplit(url).hostname or ''
    if urlsplit(url).scheme!='https' or not host.endswith('.go.kr'):
        raise SourceError('block_evidence_official_source_required')
    if not record.get('reviewed') or not re.fullmatch(r'[a-f0-9]{64}',record.get('source_sha256','')) or not record.get('checked_at'):
        raise SourceError('block_evidence_review_required')
    if not item.get('housing_manage_no') or record.get('housing_manage_no')!=item['housing_manage_no'] or record.get('pblanc_no')!=item.get('pblanc_no'):
        raise SourceError('block_evidence_project_mismatch')
    if blocks(item['address'])!={record.get('block')}:
        raise SourceError('block_evidence_identity_mismatch')
    if record.get('parcel_address'):
        if not record.get('source_excerpt') or record['parcel_address'] not in record['source_excerpt']:
            raise SourceError('block_parcel_link_evidence_missing')
        result=geo.locate(record['parcel_address'])
        result['evidence_url']=url
        return result
    if record.get('crs')!='EPSG:4326':raise SourceError('block_geometry_crs_unverified')
    ring=(record.get('geometry') or {}).get('coordinates')
    if (record.get('geometry') or {}).get('type')!='Polygon' or not isinstance(ring,list) or len(ring)!=1:
        raise SourceError('block_geometry_shape_unsupported')
    points=ring[0]
    if not 4<=len(points)<=1000 or points[0]!=points[-1]:raise SourceError('block_geometry_not_closed')
    if any(not isinstance(p,list) or len(p)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in p)
           or not (124<=p[0]<=132 and 33<=p[1]<=39) for p in points):raise SourceError('block_geometry_coordinates_invalid')
    def orientation(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    edges=list(zip(points,points[1:]))
    for i,(a,b) in enumerate(edges):
        if a==b:raise SourceError('block_geometry_degenerate')
        for j,(c,d) in enumerate(edges):
            if j<=i+1 or (i==0 and j==len(edges)-1):continue
            if orientation(a,b,c)*orientation(a,b,d)<=0 and orientation(c,d,a)*orientation(c,d,b)<=0:
                if max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0])) and max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1])):
                    raise SourceError('block_geometry_self_intersection')
    cross=[a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:])]
    area=sum(cross)
    if abs(area)<1e-12:raise SourceError('block_geometry_degenerate')
    x=sum((a[0]+b[0])*c for a,b,c in zip(points,points[1:],cross))/(3*area)
    y=sum((a[1]+b[1])*c for a,b,c in zip(points,points[1:],cross))/(3*area)
    inside=False
    for a,b in zip(points,points[1:]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    if not inside:raise SourceError('block_geometry_representative_point_outside')
    if not record.get('lawd_codes') or any(not re.fullmatch(r'\d{5}',c) for c in record['lawd_codes']):
        raise SourceError('block_geometry_district_unverified')
    return dict(coordinates=[y,x],evidence_url=url,lawd_codes=record['lawd_codes'],address=item['address'])
