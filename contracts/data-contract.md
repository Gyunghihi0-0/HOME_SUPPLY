# 용인 장애인 특별공급 데이터 계약 1.0.0

소비 경로는 `docs/data/latest.json`입니다. 구현 스키마는 `latest.schema.json`이며 JSON Schema 2020-12를 사용합니다. `example-latest.json`은 실제 수집 결과에서 가져온 예시입니다. 합성 가격이나 가상 공고를 운영 데이터로 제공하지 않습니다.

## 공통 규칙

- 금액은 원 단위 숫자, 면적은 전용면적 ㎡, 거리는 m입니다. 미확인 값은 `null`; `0`으로 대체하지 않습니다.
- 시각은 `2026-10-18T08:17:00+09:00`처럼 시간대가 필요합니다. 날짜만 확인된 공고일·신청일은 `YYYY-MM-DD`입니다. `apply_start_at`, `apply_end_at`, `notice_updated_at`은 날짜 또는 시각 또는 null입니다. 날짜를 JavaScript `Date`로 변환해 UTC 자정으로 표시하지 마세요.
- 날짜만 알려진 마감 당일에는 `status=unknown`, `deadline_note`를 표시합니다. 임의의 18시/23:59를 생성하지 않습니다.
- `generated_at`은 수집 시도 결과 생성 시각, `last_success_at`은 모든 필수 출처가 정상 갱신된 시각입니다. 한 번도 전체 정상 갱신되지 않았다면 null입니다.
- `data_status`: `ok` 전체 정상, `partial` 공고 수집 가능하나 첨부/가격/거래/매핑 일부 미완료, `stale` 공고 출처 실패 후 기존 데이터 유지, `error` 공고 수집 실패 및 보존할 공고도 없음입니다.
- 프론트엔드는 출처별 `last_success_at` 및 현재 Asia/Seoul 시각을 비교해 36시간 초과 시 갱신 지연을 표시해야 합니다. 정적 JSON의 상태만으로 마지막 실행 이후의 스케줄 누락을 알아낼 수 없습니다.
- `sources[].status`: ok / partial / error / not_configured / not_checked. 키 미설정은 수집 결과 0건과 다릅니다. `records_count=null`은 수집 건수를 알 수 없음입니다.
- `listings`는 신청 가능 목록만의 배열이 아닙니다. unknown/ineligible/closed도 표시·필터링할 수 있습니다. 현재 버전은 선정자 명단·선정 결과를 수집하지 않습니다.

## 공고와 자격

공고 필수 필드는 JSON Schema의 `listing` 정의를 따릅니다. `region`은 확인된 시·군 이름, `district`는 구 이름입니다. `housing_type`은 private_apt/public_apt/unknown입니다. 이름은 인용부호가 있는 단지명 또는 원문 제목입니다. 한 공고가 여러 블록을 안내하면 별도 공식 식별정보 없이는 분리하지 않습니다.

`status`는 upcoming/open/closed/cancelled/unknown입니다. 기간은 기관추천 신청기간만 사용하며 청약홈 일반 청약일로 대체하지 않습니다. `notice_updated_at`은 게시판이 제공한 게시일이며, 서버의 수정시각이 확인되었다는 의미가 아닙니다. 변경 관찰시각은 `notice_history[].observed_at`입니다.

`id`는 최초 관찰된 게시물 ID에서 시작합니다. 동일한 이름과 전체 공급주소가 정확히 일치하고 공고번호가 충돌하지 않을 때에만 기존 ID로 합칠 수 있습니다. 주소 누락·후속 모집·명칭 변경·복수 블록은 자동 합치지 않습니다. 게시물 ID가 바뀐 모든 정정을 자동 식별할 수 있는 상태는 아닙니다. `notice_history`에 URL·원문 해시·게시일·관찰일·변경 유형을 보존합니다.

`eligibility.yongin_status`: eligible / ineligible / unknown. eligible은 기관추천의 지역 요건에만 해당하며 개인의 최종 자격을 보장하지 않습니다. `disability_scope`: both / mild_only / severe_only / unknown. 장애 정도별 선정 배점과 자격 제한을 구분합니다. 근거 URL과 자격 문장 없이 확정 상태를 발행하지 않습니다. 제한·예외가 있는 문장 또는 첨부 확인 실패는 unknown으로 보류합니다. 현재 구현은 명시적 제외 지역을 자동 추론하여 ineligible로 만들지 않습니다.

개인의 자격·당첨확률을 추정하지 않습니다. `conditions`에는 공개된 조건 문장만 기록합니다. 원문 전체, 담당자 이름·연락처, 선정자 명단을 JSON에 넣지 않습니다.

## 주택형과 가격

`units=[]`는 주택형이 없다는 뜻이 아니라 공식 주택형 연결이 미확인일 수 있습니다. `allocation_count`는 장애인 배정 세대수입니다. API 기관추천 전체 인원/특별공급 전체 인원으로 대체하지 않습니다.

`sale_price_basis=maximum_base_price`는 청약홈 API의 `LTTOT_TOP_AMOUNT`(만원)를 원으로 변환한 **주택형별 최고 분양금액**입니다. 특정 층·호의 확정 계약금액과 다릅니다. `exact_base_price`는 별도 공식 확인 시에만 사용합니다. 발코니·옵션·세금·금융비용을 포함한 순이익이 아닙니다.

APT API의 `SUPLY_AR`는 공급면적입니다. `area_sqm`에 넣지 않습니다. 전용면적·장애인 배정물량을 공식 모집문서와 연결한 검토 매핑이 필요합니다.

`comparables[]`: id / apartment_name / location / area_sqm / trade_date / price_krw / build_year / distance_m / source_url / collected_at. `location`은 법정동 앞5자리|법정동명|지번 형식의 아파트 위치 식별자입니다. 개인 거주주소·층·동·호 정보는 발행하지 않습니다.

## 분석 정책: 사용자 결정 2026-10-18

반경 2km, 전용면적 ±10%, 대상 단지와 준공연도 차이 10년 이내. 최근 6개월 최소 3건을 우선하고 부족하면 12개월까지 확장합니다. 경계에 걸친 인접 시군구도 `lawd_codes`에 포함해야 하며 행정구역만으로 비교하지 않습니다. 신규 단지 기준연도는 공식 입주/준공 예정연도를 검토해 기록합니다. 해당 연도 또는 좌표 근거가 없으면 계산하지 않습니다.

거래 해제 여부/해제일이 있으면 제외합니다. 위치·단지·면적·계약일·가격·층 조합의 중복을 제거하며, 별도 거래 식별번호가 없는 API의 한계로 실제 복수 거래도 보수적으로 하나로 처리될 수 있습니다. 중앙값 대비 50% 초과 편차가 있으면 이상치를 임의 삭제하지 않고 전체 계산을 보류합니다.

대표값은 선별 거래 원금액의 중앙값입니다. 면적당 가격으로 보정하지 않습니다. 가격차=중앙값−공식 분양최고금액, 비율=가격차/분양최고금액×100(소수 2자리). 분양가·전용면적·위치·표본 부족·미승인 정책·이상치 검토 시 세 가지 결과는 모두 null입니다.

신뢰도 high: 6개월 이내 10건 이상, 모두 1km 이내·면적 ±5%·준공연도 차이 5년 이내. medium: 6개월 표본 3건 이상이면서 총 5건 이상. low: 합의 기준을 통과한 최소 3건이나 위 조건 미달(12개월 확장 포함). unavailable: 계산 불가. 표본 조건의 등급이며 투자수익 보장이 아닙니다.

## 검토 매핑

`config/projects.json`의 projects를 공고 id로 인덱싱합니다. 각 항목은 `housing_manage_no`, `pblanc_no`, `official_address`, `evidence_url`, `units`, `location`을 갖습니다. units는 API MODEL_NO별 `house_ty`, `area_sqm`, `disability_allocation_count`, `evidence_url`입니다. location은 `coordinates:[위도,경도]`, `build_year`, `lawd_codes:[법정동앞5자리]`, `evidence_url`입니다.

trade_locations는 `법정동앞5자리|법정동명|지번|아파트명`으로 인덱싱하며 공식 확인한 `coordinates`, `evidence_url`을 갖습니다. 임의 좌표·준공연도·예시 매핑은 넣지 않습니다. 현재 검토 완료 매핑은 없으며 키 발급 후 공식 응답 및 문서 대조가 필요합니다. 이 단계가 끝나기 전 가격 분석 운영 완료로 표시하지 않습니다.

## 호환성

국토부 출처는 상세자료 15126468 우선으로 변경했습니다. 공개 필드와 schema_version은 변경하지 않습니다. 거래금액·전용면적·계약일·층·건축년도·취소 필드의 공식 명세와 검증은 [molit-api.md](molit-api.md)를 따릅니다. 층은 내부 검증/중복 판별에만 사용합니다. 비교 거래 source_url은 실제 사용한 상세/일반 출처를 구분합니다. 이미 발행된 JSON의 과거 출처 URL은 소급 변경하지 않습니다.

필드 제거·타입/의미 변경은 major 버전을 올립니다. 필드 추가와 enum 추가도 소비자 조율 후 minor 버전을 올립니다. 모든 변경은 handoff/backend.md에 기록합니다. `python -m scripts.validate`는 구조와 날짜 형식, 근거, 거래 수, 계산식까지 검증합니다.
