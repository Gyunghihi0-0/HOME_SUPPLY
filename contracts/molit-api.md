# 국토교통부 실거래 API 검증 및 선택

검증일: 2026-10-18. 공식 공공데이터포털 페이지에 포함된 Swagger JSON을 직접 읽어 대조했습니다. 키가 없어 인증된 실제 거래 응답은 아직 검증하지 못했습니다. 명세상 제공 필드와 실제 특정 거래에서 값이 채워지는지는 별개입니다.

우선 출처: [아파트 매매 실거래가 상세 자료 15126468](https://www.data.go.kr/data/15126468/openapi.do).

`https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev`

보조 후보: [일반자료 15126469](https://www.data.go.kr/data/15126469/openapi.do).

`https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`

요청은 두 API 모두 serviceKey, LAWD_CD(법정동 앞5자리), DEAL_YMD(YYYYMM), pageNo, numOfRows입니다. 기존 `MOLIT_SERVICE_KEY` 이름은 그대로 사용합니다. 각 서비스의 활용신청 승인은 별도로 필요합니다.

| 필요 정보 | 공식 응답 필드 | 처리 및 검증 |
|---|---|---|
| 거래금액 | dealAmount | 만원 → 원 ×10,000. 양의 정수 금액 검증 |
| 전용면적 | excluUseAr | 양의 유한 숫자 검증. 공급면적과 혼용 안 함 |
| 계약일 | dealYear, dealMonth, dealDay | 실제 달력 날짜 생성 및 검증 |
| 층 | floor | 정수 검증, 지하층의 음수 허용. 중복 판별에 사용하며 공개 JSON에는 추가하지 않음 |
| 건축년도 | buildYear | 1900년~수집연도 범위 정수 검증 |
| 거래취소 | cdealType, cdealDay | 두 필드 존재 확인. 둘 중 하나라도 값이 있으면 비교 대상에서 제외. 비어 있는 XML 태그는 정상 허용 |
| 위치 | sggCd, umdNm, jibun | 필수값·요청 시군구 일치 검증, 위치 근거와 비교 |
| 단지명 | aptNm | 필수값, 위치와 함께 식별 |
| 상세 추가 식별 | aptSeq, umdCd 등 | 공식 명세에 존재. 이번 변경에서 기존 ID·데이터 계약에 섞지 않음 |

공식 명세의 필드 목록을 `config/molit-15126468-fields.json`, `config/molit-15126469-fields.json`에 기록했습니다. 예시 거래를 실제 거래인 것처럼 저장하지 않았습니다.

## 보조 API 정책

명세상 필요한 공통 필드는 상세자료에 모두 있어 일반자료의 상시 병행 호출은 필요하지 않습니다. 기본은 상세자료만 조회합니다.

실제 응답에서 필수 키가 없거나 필수값이 비어 있으면 `trade_required_fields_missing`으로 보류합니다. 취소 필드 태그 자체가 없으면 취소되지 않았다고 추정하지 않습니다. 빈 취소 태그는 미취소 표현으로 허용합니다.

운영자가 `MOLIT_ALLOW_GENERAL_FALLBACK=true` 환경변수를 명시하고 일반자료 이용 승인을 받은 경우에만, 위 필드 누락 오류에 대해 일반자료의 **같은 시군구·같은 월 전체**를 다시 조회하고 동일 검증을 적용합니다. 상세와 일반 거래를 단지명이나 가격만으로 개별 합치지 않습니다. 일반자료에서도 필드가 누락되면 계산을 보류합니다. 비교 거래 `source_url`은 실제 사용한 API의 공식 포털 URL이며, 파이프라인은 보조 조회 사용을 partial/general_fallback_used로 알립니다.

인증/권한 오류, 호출 제한, HTTP 오류, 잘못된 숫자·날짜, 정상 0건에는 자동 전환하지 않습니다. 데이터 변경과 서비스 승인 문제를 숨기지 않기 위한 정책입니다. GitHub 기본 workflow는 fallback을 켜지 않습니다.

## 인증 후 검증

Secrets 등록 후 workflow 또는 로컬 `python -m scripts.probe_apis`를 실행합니다. 현재월 용인시 기흥구(41463)를 상세자료에서 조회하고 모든 반환 거래의 필수 필드·단위·값을 검증합니다. 0건은 통신/인증 성공일 수 있으나 실제 거래 필드 검증 완료를 의미하지 않습니다. 키·요청 URL·원문 거래 응답을 로그에 출력하지 않습니다.
