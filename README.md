# HOME_SUPPLY — 용인 장애인 특별공급 데이터

경기도 공식 기관추천 안내를 수집하여 `docs/data/latest.json`으로 제공하는 정적 백엔드입니다. 프론트엔드는 별도 세션 담당이며 이 변경에서는 수정하지 않습니다.

현재 상태: 공고 본문·PDF/HWPX 추출·근거 기반 보수적 자격 분류·스키마 검증·실패 시 보존·분석 엔진·Actions 구성 구현. 실제 API 인증 조회, 전체 첨부표 구조화, 단지별 검토 매핑, GitHub 수동 실행 및 Pages 배포는 아직 검증되지 않았습니다. 가격이 없는 공고는 null/빈 주택형 배열로 제공합니다.

## 실행

Python 3.11 이상(검증 환경 3.11). Windows에서는 `python`, 환경에 따라 `python3` 사용.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests/backend -q
python -m scripts.pipeline
python -m scripts.validate contracts/example-latest.json docs/data/latest.json
```

공식 출처에 연결할 수 있어야 합니다. 문서 원문은 메모리에서만 처리합니다. `.cache`에는 API 응답만 보관하며 공개 폴더에 포함하지 않습니다. 20시간 TTL로 정정·해제 거래를 다시 조회합니다. HTTP 상태/고정 오류 코드만 출력해 인증키가 포함된 요청 URL을 로그에 남기지 않습니다. redirects·인증·차단 우회는 하지 않습니다.

## 무료 API 키 발급과 GitHub 설정

1. [공공데이터포털](https://www.data.go.kr/)에 로그인합니다.
2. [청약홈 분양정보](https://www.data.go.kr/data/15098547/openapi.do)에서 활용신청합니다. 개발계정 승인과 해당 서비스 이용권한을 확인합니다.
3. [아파트 매매 실거래가](https://www.data.go.kr/data/15126469/openapi.do)도 별도로 활용신청합니다. 같은 키여도 서비스별 신청이 필요합니다.
4. 마이페이지 → 데이터활용 → Open API → 인증키에서 **일반 인증키(Decoding)**를 확인합니다. 이 코드는 requests가 쿼리를 인코딩하므로 Encoding 키를 그대로 넣지 않습니다.
5. GitHub `Gyunghihi0-0/HOME_SUPPLY` → Settings → Secrets and variables → Actions → New repository secret에서 `APPLYHOME_SERVICE_KEY`, `MOLIT_SERVICE_KEY` 두 개를 등록합니다. 같은 일반 키에 두 서비스가 승인되었다면 같은 값을 각각 넣을 수 있습니다. 키를 채팅·커밋·공개 JSON에 넣지 마세요.
6. 백엔드 PR 병합 후 Actions → Official data and Pages → Run workflow를 실행합니다. 로그의 출처별 상태와 결과 JSON을 확인합니다. 키만 등록해도 프로젝트 매핑이 자동 검증되는 것은 아니므로 아래 검토 단계가 필요합니다.

로컬 키 설정 후 `python -m scripts.probe_apis`로 인증과 응답 규격을 먼저 검사할 수 있습니다. 이 명령은 공고·거래 응답이나 키를 파일/로그에 공개하지 않고 출처별 성공 여부와 건수만 출력합니다. 현재월 데이터가 0건이어도 정상 응답과 인증 실패를 구분합니다.

로컬은 같은 이름의 환경변수를 사용합니다. 코드는 `.env`를 자동으로 읽지 않습니다. 브라우저에는 키를 제공하지 않습니다. 현재 두 API는 포털 안내상 무료이나 신청 트래픽·승인·이용 조건은 각 공식 페이지에서 확인하세요.

## 공식 연결과 분석 검토

[데이터 계약](contracts/data-contract.md)과 `config/projects.json`을 참고해 공고번호·주소·주택형·전용면적·장애인 배정물량·공식 좌표를 검토합니다. 단지명 유사도만으로 연결하지 않습니다. 청약홈 공급면적을 전용면적으로 사용하지 않습니다. 분양금액은 API 제공 최고금액(만원→원)임을 표시합니다.

사용자 합의 정책: 반경 2km, 면적 ±10%, 준공연도 차이 10년 이내, 6개월 최소 3건(부족하면 12개월 확장). 근거 없는 좌표나 비교 단지는 등록하지 않습니다. 정책·신뢰도는 데이터 계약에 문서화했습니다.

## 자동화와 배포

단일 `.github/workflows/backend.yml`에 테스트·수집·데이터 커밋·Pages 배포를 구성했습니다. 예약은 UTC `17 23 * * *`, 한국시간 오전 8:17 목표이며 지연·누락될 수 있습니다. 동시 실행은 대기열로 직렬화합니다. 토큰으로 만든 데이터 커밋은 재실행 루프를 만들지 않습니다. 변경 파일이 없으면 커밋하지 않습니다. 상태 확인 시각도 유의미한 데이터이므로 정상 수집을 다시 실행하면 JSON이 변경될 수 있습니다.

프론트엔드의 `docs/index.html`이 있는 경우에만 Pages artifact를 배포합니다. Settings → Pages → Source를 **GitHub Actions**로 설정하고 기존 branch-based Pages 배포는 함께 쓰지 마세요. 저장소는 현재 private이므로 계정 플랜의 private Pages 지원 여부도 확인해야 합니다. 현재 설정 변경·배포를 실행하지 않았습니다.

기본 브랜치 쓰기 정책이 bot 직접 push를 막으면 갱신 커밋은 실패합니다. workflow는 강제 push·rebase로 정책이나 다른 변경을 덮어쓰지 않습니다. 프론트엔드 개발자는 기존 별도 Pages workflow를 추가하기 전에 handoff/backend.md를 확인하세요.

`generated_at`과 출처별 `last_success_at`을 화면에 표시하고 36시간 초과 시 갱신 지연을 알립니다. 모든 필수 출처가 성공하기 전 최상위 last_success_at은 null일 수 있습니다. 수집 장애 시 이전 공고를 보존하고 workflow 실패를 알립니다.

## 제한

- 경기도 공개 목록의 앞 3페이지(최대 일반 공고 45건+상단 고정글)를 매일 확인합니다. 전체 과거 데이터 백필이나 모든 지자체 교차 수집은 아직 구현하지 않았습니다.
- HWP 바이너리는 지원하지 않습니다. PDF 이미지/OCR은 지원하지 않으며 텍스트 없는 문서는 실패로 기록합니다.
- PDF/HWPX 텍스트 추출 성공은 세대수·주택형 표 구조화 검증 성공을 뜻하지 않습니다. 자격 예외 가능성은 unknown으로 보류합니다.
- 수정 게시물의 이름·전체주소가 일치하지 않으면 자동 합치지 않습니다. 후속모집·복수블록의 검토가 필요합니다.
- 실거래 API의 해제 여부와 해제일을 제외하고 20시간마다 재조회합니다. 신고 지연과 별도 거래 ID 부재의 한계가 있습니다.
- 자격 판정은 기관추천 지역·장애정도 범위에 대한 공개 안내이며 개인 자격·실제 매도수익을 보장하지 않습니다.
