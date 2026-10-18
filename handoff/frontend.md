# 프론트엔드 인수인계

2026-10-18 · `E:\GIIIIT\HOME_SUPPLY` · `frontend/ui-dashboard`

## 환경과 범위

- `.git/HEAD`, Git status, origin 설정으로 요청된 경로·브랜치·`Gyunghihi0-0/HOME_SUPPLY` 저장소를 확인했습니다. 시작 시 작업 트리는 깨끗했습니다.
- `contracts/data-contract.md`, `contracts/latest.schema.json` 전체 정의, `handoff/backend.md`, 운영 JSON을 읽었습니다. 계약 1.0.0을 읽기 전용으로 소비합니다.
- 변경 파일: `docs/index.html`, `docs/style.css`, `docs/app.js`, `docs/assets/favicon.svg`, `tests/frontend/core.test.cjs`, `tests/frontend/browser.cjs`, `tests/frontend/browser-status.cjs`, 본 문서.
- 백엔드 코드·운영 데이터·계약·워크플로는 수정하지 않았습니다. 커밋·푸시·병합·reset·rebase를 실행하지 않았습니다.

## 구현

Vanilla JS + HTML/CSS, 외부 UI 라이브러리·폰트·인증키 없음. 상대경로 `data/latest.json` fetch로 Pages 하위 경로를 지원합니다. 기본 장애 정도는 전체이며 선택값을 저장하거나 서버에 전송하지 않습니다.

요약 카드, 장애 정도·이름·지역·모집 상태·면적·분양가 공개 여부·공급 유형 필터, 가격차·차익률·마감·최근 공고 정렬, 조건 초기화, 현재/과거/요건 제외 보기, 분석 완료/분양가 확인 대기/분석 근거 부족/자격 확인 필요 그룹을 제공합니다. 가격차·차익률 정렬은 선택한 조건에 맞는 주택형 중 해당 지표가 가장 큰 주택형을 기준으로 하며 카드에 주택형을 표시합니다. 모든 주택형은 상세에서 확인 가능합니다. 면적·공개 여부가 같은 주택형에서 함께 충족되어야 필터를 통과합니다.

자격 unknown은 경증·중증 필터에서도 확인 필요로 유지합니다. 근거 URL·문장이 없는 eligible도 보수적으로 확인 필요로 표시합니다. 요약 카드는 지역·장애 정도 요건이 확인된 전체 공고 기준이며 필터 결과와 별개입니다. 단지 ID별 공고를 프론트엔드에서 병합하지 않습니다.

날짜만 있는 마감 당일은 일정 확인 필요로 표시하며 마감시각을 만들지 않습니다. 이미 지난 날짜/시각은 종료로 옮깁니다. 취소·종료는 보존합니다. 일시 표시는 Asia/Seoul, 날짜는 원문 날짜를 보존합니다. 매분 현재시각 기준 상태와 출처 지연을 다시 평가합니다.

출처별 마지막 성공 후 36시간 경과, JSON 생성 후 36시간 경과를 갱신 지연으로 표시합니다. last_success_at=null은 전체 성공 기록 없음으로 표시합니다. not_configured의 records_count=0을 정상 수집 0건으로 제시하지 않습니다. 데이터 상태 partial/stale/error 및 로드 실패를 구분하고 새로고침 실패 시 이전 로드 자료임을 표시합니다. 지원하지 않는 schema_version은 로드 오류로 처리합니다.

상세는 native dialog로 키보드 포커스 제한·Escape·닫기·포커스 복귀를 지원합니다. 공식 공고, 자격 근거, 배점 안내, 주택형별 배정물량·금액 기준·중앙값·계산식·신뢰도·거래 목록·첨부·변경 이력을 표시합니다. 외부 링크는 HTTPS만 허용하며 새 창을 안내합니다. JSON 문자열은 HTML escape합니다. null을 0으로 변환하지 않습니다.

## 실제 데이터와 남은 백엔드 사항

운영 스냅샷은 31개 공고, partial, 모든 units가 빈 배열입니다. 실제 가격차·가격 순위는 없습니다. 공고·자격·일정 확인과 분양가 확인 대기 상태를 실제 데이터로 검증했습니다. API 인증 성공 후에도 현재 JSON에 가격이 없으므로 가격 확인 완료로 표시하지 않습니다. 프로젝트 검토 매핑·주택형·가격·거래 표본 발행은 백엔드의 기존 미완료 작업입니다. 새 계약 필드는 요청하지 않으며 변경 승인이 필요한 사항은 없습니다.

## 검증

- `node --check docs/app.js`: 통과.
- `node tests/frontend/core.test.cjs`: 35개 통과. null/음수 금액, 한국 날짜 마감 경계, unknown 자격, 장애 정도 제한, 복합 주택형 필터, 음수·0·누락 가격차 정렬, 과거/취소 분리, 안전한 링크, 출처 지연, 실제 JSON과 아래 상태 갱신 회귀를 검증했습니다. 합성 객체는 프론트엔드 테스트 안에만 있으며 운영 사이트로 전달되지 않습니다.
- `node tests/frontend/browser.cjs`: Playwright + Headless Edge로 실제 JSON, 경증/중증 전환, 검색/초기화, 과거 목록, Enter/Escape/포커스 복귀, 모바일 가로 넘침, 상세 패널, 재로드 실패·첫 로드 실패, 브라우저 예외 없음 확인.
- `node tests/frontend/browser-status.cjs`: 가상 시계·테스트에서만 가로챈 JSON으로 날짜 및 정확한 시각의 상태 전환, 미국 시간대에서 한국 자정 처리, 열린 상세 패널 갱신, 통계·필터 일치, 백그라운드 복귀, Pages 하위 경로, favicon 및 콘솔/리소스 오류 없음을 확인했습니다.
- 1440px 데스크톱·390px 모바일 스크린샷 시각 검토. CSS 변수, 레이블, skip link, focus-visible, live 상태 알림, 텍스트 상태, 모바일 카드 배치를 검토했습니다.
- `git diff --check`: 통과. 변경 범위는 프론트엔드 파일만 확인했습니다.
- 실제 스크린리더 기기 검증과 완전한 WCAG 2.2 AA 감사, 운영 가격 데이터 대조, 실제 Pages 배포는 미검증입니다.

번들 Node/Git는 PATH에 없어 절대 경로로 실행했습니다. 이 환경에서 node --test의 프로세스 격리는 EPERM이므로 `node tests/frontend/core.test.cjs`로 실행했습니다. 브라우저 실행은 sandbox 밖 로컬 테스트 권한으로 성공했습니다.

브라우저 테스트에는 Playwright와 로컬 Edge가 필요합니다. 번들 패키지 사용 시 NODE_PATH를 dependencies/node/node_modules로 설정하세요. 스크린샷은 TEST_ARTIFACT_DIR 환경변수 지정 경로 또는 OS 임시 폴더 home-supply-frontend에 생성되며 저장소에는 추가하지 않습니다.

## GitHub 반영 순서

1. 현재 브랜치에서 위 8개 파일만 검토·선택하여 git add 및 commit.
2. `git push -u origin frontend/ui-dashboard` 후 main 대상 PR 생성. 동시 백엔드 변경이 있으면 계약 1.0.0 및 실제 JSON 호환성을 리뷰합니다.
3. 병합은 사용자 승인 후 수행합니다. 별도 배포 워크플로를 생성하지 않습니다.
4. 기존 `.github/workflows/backend.yml`은 main의 docs 변경 시 실행하도록 구성되어 있습니다. 승인된 병합 후 해당 Actions와 Pages 실제 URL의 데이터 로드 및 접근성을 확인하세요. 프론트엔드 테스트는 기존 Actions에 추가하지 않았으므로 위 명령으로 별도 실행해야 합니다.

## 2026-10-18 모집 상태 자동 갱신 수정

- 이전 JSON의 upcoming을 그대로 반환하던 문제를 수정했습니다. 유효한 기관추천 기간을 한국시간으로 평가해 접수 전 upcoming → 기간 중 open → 날짜만 있는 마감 당일 unknown → 다음 날 closed로 전환합니다. 날짜만 있는 시작일 당일은 마감일 이전일 때 open입니다.
- 취소 및 명시적인 종료 상태는 보존합니다. unknown은 유효한 완전한 기간이 있을 때만 open으로 판단할 수 있으며, 기간 누락·잘못된 날짜·시간대 누락·역전된 기간·알 수 없는 상태값으로 open을 추정하지 않습니다. 한쪽 경계만으로도 확실한 접수 전/종료 판정은 가능하지만 open은 두 경계가 필요합니다.
- 정확한 시작시각부터 open이며, 정확한 마감시각은 기존 백엔드 status_at과 동일하게 해당 순간까지 포함하고 그 이후 closed입니다. 날짜만 있는 마감에는 임의 시각을 생성하지 않으며, 목록과 상세 모두 마감 시각 확인 안내를 제공합니다. 기존 deadline_note도 보존합니다.
- 날짜를 엄격히 검증하여 February 30 같은 JavaScript 자동 보정을 차단했습니다. 날짜 표시와 정렬에도 같은 검증을 적용합니다. 날짜만 있는 마감에 23:59 같은 정렬용 시각도 생성하지 않습니다. 같은 날의 시간 미확인 자료는 정확한 시간이 있는 자료 뒤에 표시합니다.
- 하나의 현재시각 스냅샷을 목록·필터·요약에 적용합니다. 30초마다 및 visibilitychange/focus/pageshow 복귀 시 재평가합니다. 열린 상세는 상태·안내 텍스트만 갱신해 스크롤과 포커스를 유지합니다. 변화가 없을 때는 목록 DOM을 재작성하지 않습니다. 상태 변화로 원래 버튼이 사라지면 상세를 닫을 때 결과 영역으로 포커스를 돌려줍니다.
- 로컬 SVG favicon과 상대경로 링크를 추가했습니다. /HOME_SUPPLY/assets/favicon.svg 응답 및 favicon 404 해소를 실제 Edge에서 확인했습니다.
- 운영 JSON·백엔드·계약·Actions는 수정하지 않았고 Commit/Push/Merge/브랜치 변경도 실행하지 않았습니다.


## 2026-10-18 통합 및 Pages 배포 준비

사용자가 Commit/Push/Merge/배포를 승인했습니다. 로컬 커밋 2186075는 보존했고 Git 인증이 없어 사용자의 추가 승인에 따라 GitHub 커넥터로 최신 main 기준의 프론트엔드 커밋 286f23e를 발행했습니다. PR #2를 병합한 커밋은 f7cc96f입니다. 저장소 공개 전환의 전체 소스·이력 공개 영향을 안내한 뒤 사용자가 명시적으로 승인하고 직접 공개 전환 및 Pages Source=GitHub Actions를 설정했습니다.

기존 수집이 30분 넘게 지속되어 사용자가 기존 backend.yml의 수동 refresh_data 옵션 추가를 승인했습니다. PR #3(804e623 병합)은 boolean 기본값 true와 수동 false일 때만 수집을 건너뛰는 조건 7줄만 추가합니다. 예약/push 수집, JSON 검증, 기존 배포·권한·Secrets는 그대로입니다. YAML 및 조건 진리표 검사와 PR CI가 통과했습니다. 새 워크플로는 만들지 않았습니다. 수집을 끈 배포는 기존 JSON의 생성시각 및 partial 상태를 보존합니다.

초기 배포 실행 39093487045는 수집·JSON 검증까지 완료했지만, 실행 중 main에 옵션 PR이 병합되어 기존 checkout의 데이터 push가 non-fast-forward로 거절됐습니다. 강제 push하지 않았고 기존 운영 JSON은 보존됐습니다. 이 실행의 deploy는 skipped입니다. 기존 백엔드 workflow의 데이터 push는 동시 main 변경 시 안전하게 실패하지만 자동 재시도하지 않는 한계가 있습니다.

현재 필요한 사용자 단계: Actions → Official data and Pages → Run workflow → main → Refresh official data before deployment 체크 해제 후 실행. 연결 도구에는 workflow_dispatch 및 취소 기능이 없고 로그인된 브라우저 세션도 없어 이 클릭은 사용자가 수행해야 합니다. 실행 후 Pages 성공 및 공개 URL smoke test를 확인해야 배포 완료입니다. 공개 저장소/Pages 활성화만으로 배포 완료로 간주하지 않습니다.

로컬 main은 승인된 병합 결과로 fast-forward 동기화했고 기존 frontend/ui-dashboard 로컬 커밋은 삭제하거나 재작성하지 않았습니다.
