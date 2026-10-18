# 백엔드 인수인계

## 작업 환경 및 협업

2026-10-18, 저장소 `Gyunghihi0-0/HOME_SUPPLY`, 기준 main 커밋 `32db51de5f69ad5c15321540af1bfe32abdfb104`. 확인 시 README만 존재했습니다. 로컬 Git 실행 파일이 없어 GitHub 커넥터로 독립 브랜치 `backend/official-data-pipeline`을 생성했습니다. 로컬 소스는 `E:\GPT_SET`에 작성했습니다. 프론트엔드 파일은 만들거나 수정하지 않았습니다. main에는 직접 반영하지 않습니다.

## 프론트엔드 연결

- `contracts/latest.schema.json`과 `contracts/data-contract.md`가 계약 1.0.0입니다.
- 실제 경기도 수집 JSON은 `docs/data/latest.json`; 실제 공고 발췌 예시는 `contracts/example-latest.json`입니다.
- 기관추천 일정은 날짜 또는 시간대 포함 시각 또는 null입니다. 마감 날짜만 아는 당일은 unknown으로 처리합니다.
- `eligibility.eligible`은 용인시 거주자의 지역 요건에 한정하며 개인 청약 자격을 보장하지 않습니다.
- 가격 데이터가 미확인일 때 `units=[]`일 수 있습니다. 최고 분양금액 기반 가격차이며 순매도수익이 아닙니다.
- 전체 성공 전 `last_success_at=null`이 정상입니다. 출처별 상태를 표시하고 클라이언트에서 현재 시각 대비 36시간 경과를 확인해야 스케줄 누락을 표시할 수 있습니다.
- 가격 숫자 null을 0원으로 표시하지 마세요. unknown 자격을 신청 가능으로 표시하지 마세요.
- backend.yml이 단일 Pages 배포를 담당하도록 작성했습니다. 별도 frontend Pages 배포 workflow와 중복 실행하지 마세요. docs/index.html이 없으면 배포하지 않습니다.

## 확인한 공식 출처

1. https://www.gg.go.kr/bbs/board.do?bsIdx=504&menuId=1878 — HTTP 200. HTML은 목록 로딩 껍데기이며 `/assets/js/board-list-default.min.js`에서 공개 `/ajax/board/getList.do` POST 호출, offset/limit 사용을 확인했습니다. 실제 total 3756 응답을 확인했습니다.
2. https://www.gg.go.kr/robots.txt — HTTP 200. /bbs, /ajax/board, /assets/js, /cmmn/download 경로는 현재 금지되지 않았습니다. /common, /site, /down 등 금지 경로는 접근하지 않습니다. 매 실행에서 규칙을 재확인합니다. robots 허용이 모든 재이용 권리를 보장하는 것은 아닙니다.
3. https://www.data.go.kr/data/15098547/openapi.do 및 해당 페이지의 공식 Swagger `https://infuser.odcloud.kr/api/stages/37000/api-docs?1643022751478` — APT 상세 및 주택형 API, 인증 방식 serviceKey/Authorization, 최고 분양금액 만원 단위 확인. 무키 실제 요청은 401 인증키 필수 응답을 확인했습니다.
4. https://www.data.go.kr/data/15126469/openapi.do — 페이지 내 공식 Swagger에서 `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`, serviceKey/LAWD_CD/DEAL_YMD/pageNo/numOfRows, 해제 필드 및 거래금액 만원 단위를 확인했습니다. 인증된 조회는 아직 하지 못했습니다.
5. 용인시 공식 공고 URL의 검색/원문 접근은 조사했지만 현재 지자체별 수집기는 경기도만 구현했습니다. 용인시·3개 구청·LH·GH·청약홈 모집공고 PDF 교차검증 수집은 미구현입니다.

## 구현한 기능

공식 공개 목록/본문 수집, 신청기간 추출, PDF/HWPX 메모리 내 텍스트 추출, 선정자 명단 제외, 자격·배점 구분, 원문 근거 문장, 변경 해시 이력, 같은 게시물 및 정확한 이름/주소가 있는 정정 공고의 제한적 통합, 시간대/날짜 구분, 이전 데이터 보존, 원자적 JSON 발행, 엄격한 스키마 및 계산식 검증.

청약홈·국토부 API 클라이언트는 페이지 처리·인증키 환경변수·오류 코드·단위 변환·캐시·재시도를 구현했습니다. 검토된 공고번호/주택관리번호/주소/주택형 매핑만 연결합니다. 별도 DB/상시 서버는 없습니다.

가격 엔진은 좌표 근거·전용면적·준공연도가 확인된 거래만 선택하고, 취소/중복을 제외하여 중앙값과 가격차를 계산합니다. 최신 주택형 가격을 받았으나 거래 조회가 실패하면 이전 가격차를 새 가격에 그대로 붙이지 않습니다.

## 사용자 결정

2026-10-18: 반경 **2km**, 전용면적 **±10%**, 대상 단지 준공연도와 **10년 이내** 차이. 최근 6개월 3건 이상, 부족하면 12개월 확장. `config/analysis.json`에 승인 기록. 신뢰도와 이상치 계산 보류 기준은 계약 문서에 정의했습니다.

2026-10-18: 사용자는 API 키가 아직 없다고 답변했습니다. README에 두 서비스별 활용신청과 Decoding 키, `APPLYHOME_SERVICE_KEY`/`MOLIT_SERVICE_KEY` Secrets 등록 절차를 제공했습니다. 키를 대화나 저장소에 받지 않습니다.

## 검증 및 남은 작업

자동 테스트: 날짜/시간대, 자격 근거, 배점과 제한 구분, 정정 이력, 만원→원, 취소/중복, 거리/면적/준공연도, 최소 표본, 12개월 확장, 이상치 보류, 실패 보존, 스키마 오류 시 기존 파일 보호. 실제 API 키가 없어 인증 테스트는 미실시입니다.

최종 실제 실행(2026-10-18): 공식 목록 3페이지에서 정정 통합 후 공고 레코드 **31개**. PDF/HWPX 텍스트 추출 **51개 성공**, **3개 실패**, **HWP 1개 미지원**. 신청기간 **21개** 추출. 용인시 지역 요건 eligible 및 경·중증 both **13개**, 확인 보류 **18개**. 모집 상태 upcoming 4 / open 4 / closed 13 / unknown 10. 미확인 일정·첨부 예외·표 구조화 검토는 자동 생성하지 않았습니다. 두 API 키와 프로젝트 매핑이 없어 data_status=partial, 실제 가격차 없음. 일반 접수기준 공지 1개가 단지 공고에 포함되던 초기 문제는 필터 수정 후 최종 데이터에서 제외했습니다.

최종 로컬 자동 테스트 **14개 통과**. 실제 JSON 및 실제 공고 발췌 예시의 스키마·추가 의미 검증 통과. `probe_apis`는 두 missing-key 오류를 안전하게 보고하고 종료코드 1로 종료하는 것을 확인했습니다. 외부 API 인증 성공 테스트와 GitHub Actions 성공으로 오해하지 마세요.

운영 완료가 아닌 항목:

- API 키 발급/서비스 승인/Secrets 등록과 인증 응답 테스트.
- `config/projects.json`에 실제 검토된 매핑 등록. 현재 비어 있습니다. 좌표·전용면적·장애인 배정물량·공고번호를 임의 생성하지 않았습니다.
- 첨부 텍스트의 표 구조화 및 모든 예외 판독. parse_status=parsed는 텍스트 추출 성공일 뿐 전체 필드 검증 완료가 아닙니다.
- HWP 바이너리/OCR 미지원. PDF 텍스트 실패 시 unknown 및 partial로 보류합니다.
- 신규 공고번호·이름·주소 변경이 동시에 발생하는 정정/후속모집을 완전 자동 연결하지 않습니다.
- 실제 매물별 분양가·실거래 가격 대조 및 가격차 운영 데이터 검증. 현재 실제 가격차를 제공하지 않습니다.
- GitHub Actions workflow_dispatch·예약 실행·Pages 배포 실증. PR 병합 및 Secrets/Pages 설정 후 확인 필요합니다. 현재 private 저장소의 Pages 플랜 조건도 확인해야 합니다.

실패를 성공이나 공고 0건으로 표시하지 않습니다. 현 상태를 운영 가능한 전체 시스템 완성으로 보고하지 않습니다.

## 2026-10-18 후속 변경: 국토부 상세자료 우선

사용자 요청으로 국토부 기본 조회를 상세자료 **15126468**의 RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev로 전환했습니다. `MOLIT_SERVICE_KEY` Secret 이름은 유지합니다. 두 공식 포털의 내장 Swagger를 직접 조회해 거래금액(만원), 전용면적, 계약일(년/월/일), 층, 건축년도, 해제여부·해제일, 위치 필드를 확인했습니다. 상세에는 단지일련번호·법정동/도로명 코드도 있습니다. 검증한 필드 명세는 config/molit-15126468-fields.json 및 config/molit-15126469-fields.json에 기록했습니다.

필수 키/값 누락은 더 이상 조용히 건너뛰지 않고 오류로 보류합니다. 취소 필드의 빈 태그는 허용하지만 태그 누락을 미취소로 추정하지 않습니다. 층은 정수 검증·중복 판별에만 사용하고 기존 공개 계약을 유지합니다. 상세의 필수 필드 누락 시에만 선택적으로 일반자료 같은 월 전체를 재조회하도록 구현했으며 기본 비활성입니다. 인증 오류·할당량·정상 0건·값 오류에는 보조 조회하지 않습니다. 보조 조회 출처는 거래별 URL과 partial/general_fallback_used로 식별됩니다.

변경 후 로컬 테스트 **27개 통과**, 기존 JSON/예시 검증 통과. 아직 키가 없어 인증된 실제 거래 응답 검증은 미실시입니다. 기존 운영 스냅샷의 과거 일반자료 출처 URL은 실제로 상세를 조회한 것으로 오인되지 않도록 소급 변경하지 않았습니다. 상세자료 활용신청 후 GitHub Settings → Secrets and variables → Actions의 기존 MOLIT_SERVICE_KEY 값을 등록/수정하는 절차를 README에 추가했습니다. 공식 응답 필드와 일반자료 검토 근거는 contracts/molit-api.md에 정리했습니다.
