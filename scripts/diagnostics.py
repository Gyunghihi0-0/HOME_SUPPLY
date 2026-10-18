"""Public per-notice stage diagnosis, with explicit evidence limits."""
from collections import Counter
from difflib import SequenceMatcher
from scripts.matching import compact,select_project,canonical_name
from scripts.http_client import SourceError

LABELS={
 'sale_price_and_exclusive_area_pending':'공식 분양가·전용면적 연결 대기',
 'insufficient_verified_data':'공식 분석 근거 확인 대기',
 'exclusive_area_unverified':'정확한 공식 전용면적 미확인',
 'verified_coordinates_pending':'공식 위치 좌표 검증 대기',
 'price_area_or_verified_location_missing':'가격·전용면적·위치 근거 미확인',
 'official_project_not_in_catalog':'조회 기간의 청약홈 API에 해당 사업 없음 · 미공고 확정 아님',
 'official_project_name_mismatch':'동일 위치 후보의 공식 단지명 불일치',
 'official_project_address_mismatch':'공식 주소·지번 근거 불일치 또는 불충분',
 'official_project_block_mismatch':'개발지구 블록 불일치',
 'official_project_multiple_candidates':'동일 근거의 청약홈 후보가 여러 개',
 'official_announcement_round_unverified':'기존 사업번호·현재 모집차수 연결 근거 미확인',
 'official_unit_type_not_found':'기관추천 주택형에 대응하는 공식 모델 없음',
 'official_unit_type_ambiguous':'주택형 후보가 여러 개',
 'official_exclusive_area_conflict':'공식 전용면적 근거끼리 충돌',
 'official_exclusive_area_missing':'정확한 공식 전용면적 미확인',
 'official_block_geometry_missing':'개발지구 좌표·지번 연결 근거 미확인',
 'kakao_exact_address_not_found':'공식 주소의 카카오 검색 결과 없음',
 'disability_allocation_unverified':'장애인 배정물량 미확인',
 'fewer_than_three_verified_trades':'반경·면적·연식 기준을 충족하는 실거래 최소 3건 미달',
 'outlier_review_required':'비교 거래 가격 편차 검토 필요',
 'verified':'실제 연결 성공',
}

def root_id(value):return value.split('_p',1)[0]

def metrics(data,cohort=None):
    rows=[r for r in data['listings'] if cohort is None or root_id(r['id']) in cohort]
    units=[u for r in rows for u in r['units']]
    return dict(notices=len({root_id(r['id']) for r in rows}),project_records=len(rows),
        matched_projects=len({(r['housing_manage_no'],r['pblanc_no']) for r in rows if r['housing_manage_no'] and r['pblanc_no']}),
        units=len(units),priced_units=sum(u['sale_price_krw'] is not None for u in units),
        exact_area_units=sum(u['area_sqm'] is not None for u in units),
        coordinate_projects=sum(r['location_verified'] for r in rows),
        verified_trade_records=len({t['id'] for u in units for t in u['comparables']}),
        gap_units=sum(u['estimated_gap_krw'] is not None for u in units))

def report(data,capture,cohort=None):
    records=[];catalog=capture['projects']
    for item in data['listings']:
        if cohort and root_id(item['id']) not in cohort:continue
        stages={'notice':'verified' if item['notice_url'] else 'notice_missing'};project=None
        try:project=select_project(item,catalog);stages['project']='verified'
        except SourceError as exc:stages['project']=str(exc)
        details=[]
        for unit in item['units']:
            reason=str(unit.get('analysis_reason') or '').split(';')[0]
            code='verified' if unit['estimated_gap_krw'] is not None else reason
            if not unit['area_sqm'] and unit['sale_price_krw']:code='official_exclusive_area_missing'
            if unit['area_sqm'] and unit['sale_price_krw'] and not item['location_verified']:
                code='official_block_geometry_missing' if 'BL' in (item['address'] or '').upper() or '블록' in (item['address'] or '') else 'kakao_exact_address_not_found'
            details.append({'type':unit['type_id'],'price':unit['sale_price_krw'],'exclusive_area':unit['area_sqm'],
                'allocation':unit['allocation_count'],'gap':unit['estimated_gap_krw'],'code':code,'label':LABELS.get(code,code)})
        # Similarity creates review candidates only; it never changes select_project().
        ranked=sorted(catalog,key=lambda row:SequenceMatcher(None,canonical_name(item['name']),canonical_name(row.get('HOUSE_NM'))).ratio(),reverse=True)[:3]
        candidates=[{'name':r['HOUSE_NM'],'address':r['HSSPLY_ADRES'],'manage_no':r['HOUSE_MANAGE_NO'],
            'similarity':round(SequenceMatcher(None,canonical_name(item['name']),canonical_name(r['HOUSE_NM'])).ratio(),3)} for r in ranked]
        code=stages['project']
        if code=='official_project_not_in_catalog' and item.get('housing_manage_no'):
            code='official_announcement_round_unverified';stages['project']=code
        category='실제 연결 성공' if project else '공식 정보가 아직 없음' if code=='official_project_not_in_catalog' else '추가 개발 필요'
        records.append({'id':item['id'],'notice_id':root_id(item['id']),'name':item['name'],'notice_url':item['notice_url'],
            'stages':stages,'category':category,'project_label':LABELS.get(code,code),
            'catalog_window_only':code=='official_project_not_in_catalog','units':details,'review_candidates':candidates,
            'coordinate_verified':item['location_verified'],'collection_issues':item['collection_issues']})
    return {'observed_at':capture['observed_at'],'catalog_cutoff':capture.get('cutoff'),'catalog_records':len(catalog),
        'evidence_run':capture['verification_run'],'metrics':metrics(data,cohort),
        'classification_counts':dict(Counter(r['category'] for r in records)),
        'limitations':['API 조회 기간 내 부재는 정식 공고 미발표를 확정하지 않음','이름 유사도 후보는 자동 확정에 사용하지 않음'],
        'records':records}
