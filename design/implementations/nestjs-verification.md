# NestJS 검증 계획

Status: 네이티브·SQLite·복구 자동 시험 및 저장 snapshot runtime 경계 검증 기록 · 2026-09-16

이 문서는 [구현 설계](nestjs.md)의 통과 조건과 이후 실행 증거를 소유합니다.
FastAPI의 시험 통과를 NestJS의 검증 결과로 대신하지 않습니다.

## 초기 기반과 HTTP

| ID | 시험 | 통과 조건 |
| --- | --- | --- |
| N-BOOT-01 | 새 디렉터리에서 고정 도구로 설치·빌드 | lockfile 변화 없이 설치되고 `dist/`의 앱이 지정 포트에서 시작합니다. |
| N-BOOT-02 | 설정 누락·잘못된 값 | listen 전에 실패하며 비밀값을 오류·로그에 노출하지 않습니다. |
| N-DI-01 | clock Provider 교체 | 고정 시간의 인사 결과가 나오고 다른 앱 인스턴스에 override가 퍼지지 않습니다. |
| N-LIFE-01 | 중간 자원 준비·listen 실패 | 준비 완료 상태가 남지 않고 생성된 자원이 한 번씩 해제됩니다. |
| N-LIFE-02 | 정상 종료·처리 중 종료 | readiness가 꺼지고 설정한 대기 정책 뒤 연결·timer가 종료됩니다. 프로세스 잔류가 없습니다. |
| N-HTTP-01 | 정상·DTO 검증 실패·잘못된 JSON·업무 오류 | `data`와 Problem의 status·media type·공개 코드가 공통 계약과 맞고 parser 실패도 422로 변환됩니다. |
| N-HTTP-02 | 404·405·의미 있는 오류 헤더 | Problem과 `Allow`·`Retry-After`가 보존됩니다. OpenAPI에도 등록됩니다. |
| N-HTTP-03 | health·metrics·204·stream | 업무 envelope가 추가되지 않고 이미 시작한 응답에 재응답하지 않습니다. |
| N-HTTP-04 | DB model·예외·입력 원문 주입 | 비공개 속성·검증 원문·예외 메시지가 응답에 나타나지 않습니다. |
| N-HTTP-05 | 정상·Pipe 이전 오류·라우팅 오류 | `X-Request-ID`가 유지되고 Problem의 `request_id`·로그 ID가 일치합니다. |

Service의 작은 정책은 일반 객체·함수 시험으로 확인합니다. Nest 조립은 `Test.createTestingModule()`과
`overrideProvider()`로, HTTP 계약은 실제 앱의 Pipe·Filter 설정을 포함한 요청으로 검증합니다.
고정 CLI가 생성한 runner와 HTTP 시험 도구를 우선합니다.
[Nest Testing](https://docs.nestjs.com/fundamentals/testing), 확인일: 2026-09-08.

## 관측과 연결 정리

| ID | 시험 | 통과 조건 |
| --- | --- | --- |
| N-OBS-01 | 2개 앱과 동시 요청 | registry·요청 ID가 섞이지 않고 요청 요약·HTTP 지표가 중복되지 않습니다. |
| N-OBS-02 | 정상 `finish`·조기 `close`·업무 실패 | 전송 완료와 실행 결과가 구분됩니다. 클라이언트 수신 보장을 주장하지 않습니다. |
| N-OBS-03 | logger·metrics 실패 | 원래 응답과 자원 정리가 유지되고 관측 실패를 확인할 수 있습니다. |
| N-OBS-04 | 실제 수집과 서버 중지 | `/metrics`·Prometheus·Grafana 값이 대조되고 수집 단절이 정상 0으로 보이지 않습니다. |
| N-DB-01 | 연결 점유·pool 고갈·반환 | 실제 연결 수·획득 시간·timeout·회복이 선택한 DB 도구의 상태와 맞습니다. |
| N-DB-02 | 저장·commit·rollback 실패 | 업무 결과와 transaction 지표가 맞고 연결을 반환합니다. DB 잠금 실패와 pool timeout을 구분합니다. |
| N-DB-03 | transaction runner callback·acquire·begin·release·metrics 실패 | 원래 오류와 commit/rollback/cleanup 결과를 구분하고 획득한 lease를 항상 반환하며 관측 실패가 결과를 덮지 않습니다. |

Node socket 종료가 진행 중 Promise나 DB 질의를 자동으로 취소한다고 가정하지 않습니다.
연결 중단 시험은 이미 확정된 변경과 계속 실행 중인 작업도 함께 확인합니다.

## 예약·동시성·멱등성

DB 단계에서 선정한 실제 DB의 독립 연결과 독립 프로세스로 검증합니다.
프로세스 메모리 대역·mock 저장소 시험만으로 다음 항목을 통과시키지 않습니다.

| ID | 시험 | 통과 조건 |
| --- | --- | --- |
| N-RES-01 | 순차 예약·중간 저장 실패 | 성공은 한 번 차감하고 실패는 재고·예약·멱등 결과를 함께 rollback합니다. |
| N-RES-02 | 재고 1개에 서로 다른 동시 요청 | 성공·예약 한 건, 재고 0이며 음수·부분 변경이 없습니다. |
| N-RES-03 | 같은 키 순차·동시 요청 | 한 번 차감하며 같은 입력의 재요청에 합의한 기존 성공 결과를 반환합니다. |
| N-RES-04 | 같은 키·다른 입력 | 기존 결과를 바꾸지 않고 계약된 충돌 응답을 반환합니다. |
| N-RES-05 | rollback 후 재시도 | 같은 키로 다시 처리할 수 있고 실패의 부분 상태가 남지 않습니다. |
| N-RES-06 | commit 뒤 응답 유실·프로세스 재시작 | 이미 확정된 예약을 재생하며 중복 차감하지 않습니다. |
| N-RES-07 | commit 전후 프로세스 강제 종료 | 미확정 변경의 rollback과 확정 결과의 재생을 구분합니다. |
| N-RES-08 | 저장 snapshot의 shape·ID 타입·시각 손상 | HTTP 성공으로 재생하지 않고 500을 반환하며 재고·예약·멱등 키를 추가 변경하지 않습니다. |

DB/ORM을 바꾸면 해당 DB에서 이 표를 다시 수행합니다. 동시성 시험은 처리량·p95 보장의 근거가 아니며
부하 목표와 환경은 [Runtime Review](../runtime-review.md) 기준으로 따로 기록합니다.

## 실행 기록에 남길 내용

구현 commit·Node/Nest/DB 버전, 실제 명령·시각, 케이스별 결과와 미검증 범위를 기록합니다.
첫 기반이 완료되면 실행 가능한 안내를 사용 가이드에 연결하고, 이 문서는 검증 증거를 유지합니다.
아래 실행 기록은 NestJS 자체 시험 결과입니다. 컨테이너·Prometheus·Grafana 결과로 확대하지 않습니다.

## 실행 결과 — 2026-09-08

코드 checkpoint `6e077ca`, Node 24.20.0 LTS, Nest 12.0.1, CLI 12.0.0, pnpm 12.3.4,
TypeScript 6.0.3, Vitest 4.1.11, Drizzle 0.45.2, drizzle-kit 0.31.10,
better-sqlite3 13.0.3, SQLite engine 3.53.4 (`sqlite_version()`), tarn 3.1.2입니다.
macOS arm64에서 실행했으며 최종 자동 시험은 2026-09-08 11:29 KST에 통과했습니다.

단계별 commit은 `56cf0c7` 공식 Nest CLI 생성물 보존, `521e098` 설정·DI·수명,
`5c3eb31` HTTP·관측·SQLite 예약·복구 시험, `6e077ca` 중앙 리뷰 반영·컨테이너 시작 파일입니다.

`ts/nestjs/`에서 실행한 명령과 결과:

| 명령 | 결과 |
| --- | --- |
| `node scripts/toolchain.mjs install --frozen-lockfile` | 통과, lock 유지 |
| `node scripts/toolchain.mjs build` | 통과, ESM `dist/` 생성 |
| `node scripts/toolchain.mjs typecheck` | 통과 |
| `node scripts/toolchain.mjs test` | 5 files, 32 tests 통과 (unit·실제 DB·독립 프로세스) |
| `node scripts/toolchain.mjs test:e2e` | 2 files, 15 tests 통과 |
| `node scripts/toolchain.mjs lint` | oxlint 통과 |
| `node scripts/toolchain.mjs peers check` | peer dependency 문제 없음 |
| `node scripts/toolchain.mjs exec drizzle-kit generate --name reservations` | 3개 table의 SQL·snapshot·journal 공식 생성 및 검토 |
| `node scripts/toolchain.mjs db:migrate` | 임시 파일 DB 최초 적용·재실행 통과 |
| `node scripts/toolchain.mjs db:seed widget 1` | seed와 기존 재고 보존 확인 |

`test/integration/reservations.spec.ts`: 순차·동시 예약, 품절, 없는 상품, 입력/키 검증,
저장 중간 실패·멱등 저장 실패, **deferred foreign key를 통한 실제 COMMIT 실패**, rollback 실패 시 dirty 연결 폐기,
독립 앱 연결 경합, 동일키 재생·다른 입력 충돌, 실제 SQLite 잠금 대기 중 timer·health 응답,
pool timeout·반환·회복, worker 강제 종료와 원자성 검증입니다.

`test/integration/processes.spec.ts`: 독립 Node 프로세스 두 개의 다른 키·동일키·입력 충돌 경합,
COMMIT 직전/직후 SIGKILL, 응답 socket 유실, 프로세스 재시작 재생,
SIGTERM 진행 요청 drain, 종료 기한에서 socket만 닫고 DB 확정을 기다리는 동작을 확인했습니다.
COMMIT 뒤 종료를 rollback으로 분류하지 않습니다. 임의 장애 timing 전체를 증명하지는 않습니다.

`test/integration/lifecycle.spec.ts`: 실제 schema 누락 초기화 실패의 pool 정리,
DB 관측 실패에도 확정 상태·연결 반환 유지, DB 비활성 readiness 정상과
예약 GET/POST 404·OpenAPI/DB provider/DB metric 미등록을 확인했습니다.
`test/unit/observation.spec.ts`: numeric status·한정 상태, 앱 registry 격리,
닫힌 socket 이후 업무 종료 관측과 중복 방지, 미지원 method의 `OTHER` 라벨을 확인했습니다.

HTTP 시험은 422의 공개 위치·고정 코드·원문 제외, 404·405/Allow, 429/Retry-After,
서버 생성 32자리 request ID, 잘못된 JSON parser 실패, 500·stream 실패 후 재응답 방지,
health·metrics·204·OpenAPI 예외, 라벨 cardinality와 logger/metrics 실패 격리를 확인합니다.
추가 시험 경로 `/test/items/:id`의 서로 다른 두 ID는 공개 Express `req.route.path`를 통해
같은 template 라벨에 2건으로 집계되고 원문 ID는 metric에 포함되지 않았습니다.
업무 API의 405 판정은 정적 Swagger 경로에 한정되며 매개변수 경로 405·다른 adapter는 미검증입니다.

## 실제 포트·JSON 출력

18083 미점유를 확인한 뒤 임시 파일 DB에서 공식 migration과 seed를 실행했습니다.
실제 서버 PID 27230에서 readiness 200, 예약 201(false), 동일키 재생 201(true),
동일 성공 data·HTTP/DB metrics를 확인했습니다. stdout JSON 2건을 직접 파싱했고 status는 숫자이며
상품/멱등키 원문이 없었습니다. stderr는 비었고 소유 PID에 SIGTERM을 보내 종료·포트 해제를 확인했습니다.

단일 smoke RSS는 303632 KiB(약 297 MiB)였습니다. 기본 pool 상한 2는 지연 생성됩니다.
이 값은 처리량·최대 부하·컨테이너 메모리 예산 보장이 아닙니다.
컨테이너의 소규모 요청·재시작 후 단일 측정은 50.45 MiB / 한도 512 MiB였습니다.

## 복사 실행

새 임시 디렉터리에 구현을 복사해 node_modules·dist 없이 frozen 설치와 build를 수행했습니다.
lockfile SHA-256은 전후 동일했습니다. 이후 `src`를 실행 경로에서 옮긴 상태에서도 migration 2회·seed와
빌드된 앱의 OS 임시 포트 55473 예약 201이 통과했습니다. 이 검증은 macOS native 복사 실행이며
Linux 컨테이너 검증을 대신하지 않습니다.

## 로컬 통합 검증

중앙 Compose는 `ts/nestjs` context와 `.node-version`에서 읽은 `NODE_VERSION` build arg,
`SERVER_HOST=0.0.0.0`·`SERVER_PORT=3000`, 게시 포트 `127.0.0.1:18084:3000`을 연결합니다.
DB 사용 시 `DB_PRIMARY_URL=file:/app/data/template.db`와 UID/GID 10001이 쓸 수 있는 volume이 필요합니다.
runtime COPY는 UID/GID 10001 소유로 설정해 pnpm workspace 파일의 생성 권한 0600도 읽을 수 있습니다.
시작 script는 공식 migration 후 앱을 exec하며 seed는 명시적으로 실행합니다.

2026-09-08 main 통합에서 공식 Compose 명령으로 image build와 UID 10001 실행을 확인했습니다.
DB 비활성 시 health 200·예약 GET/POST 404·OpenAPI 제외, 활성 시 migration·seed·예약 201을 확인했습니다.
입력 오류 3종은 422·Problem·request ID, GET 예약은 405·Allow를 반환했습니다.
원래 body 재생·다른 입력의 동일 키 409·없는 상품 404가 통과했습니다.
재고 3에서 최초 예약 후 6개 병렬 요청은 성공 2개·품절 4개였고, 컨테이너 재시작 후 원래 body를 재생했습니다.
Prometheus job=nestjs UP·HTTP/DB 지표·Grafana query와 MkDocs strict build를 확인했습니다.
N-OBS-04·Task 8의 로컬 통합 범위까지 완료했습니다.

## Task 9 검증 — 2026-09-08

기준 `1b3cc63`에서 HTTP 오류 분류·공개 필드 계약·예약 업무 본문을 정리했습니다.
macOS arm64, 고정 Node 24.20.0·pnpm 12.3.4 wrapper로 13:16 KST에 실행했습니다.
`ts/nestjs/`에서 수행한 명령과 결과입니다.

| 명령 | 결과 |
| --- | --- |
| `node scripts/toolchain.mjs install --frozen-lockfile` | 통과, lockfile 변경 없음 |
| `node scripts/toolchain.mjs build` | 통과 |
| `node scripts/toolchain.mjs typecheck` | 통과 |
| `node scripts/toolchain.mjs lint` | 통과 |
| `node scripts/toolchain.mjs test` | 6 files, 40 tests 통과 |
| `node scripts/toolchain.mjs test:e2e` | 2 files, 15 tests 통과 |

새 `test/unit/validation.spec.ts`의 8개 회귀는 다른 DTO 필드의 공개 위치, 누락·null·숫자,
명시적 trim·암묵 변환 금지, unknown 필드/값 숨김·20개 제한, 검증되지만 공개하지 않은 필드를 확인합니다.
기존 시험은 변경하지 않았으며 실제 COMMIT 실패·rollback 실패의 dirty 연결 폐기·worker 종료,
독립 프로세스 동시성·멱등성·관측 종료·오류 헤더·parser 실패를 다시 통과했습니다.
Drizzle 설치 소스의 callback→COMMIT→실패 시 ROLLBACK→원래 오류 재전달 순서를 확인하고,
`bodyError` identity 판정과 Service의 동일 transaction client·release·계측 순서를 유지했습니다.
시험은 기존 fixture의 임시 SQLite DB와 OS 임시 포트를 사용했습니다.
이번 작업은 실행 중인 서비스·컨테이너·공유 수집기를 변경하거나 재검증하지 않았습니다.

## Task 10 검증 — 2026-09-15

Nest CLI 12의 `nest generate provider --help`로 `--flat`·`--no-spec` 지원을 확인한 뒤
`database/transaction-runner` provider를 공식 generator로 만들고 DB-enabled DI에만 등록했습니다.
`TransactionClient`는 database runner가 소유하며 Repository가 runner의 callback client를 받습니다.
Service는 `reserveInTransaction`의 업무 흐름을 유지하고 `TransactionRunner.run<T>()`만 호출합니다.

macOS arm64, 고정 Node 24.20.0·pnpm 12.3.4 wrapper에서 수행한 결과입니다.

| 명령 | 결과 |
| --- | --- |
| `node scripts/toolchain.mjs exec vitest run test/unit/transaction-runner.spec.ts` | 1 file, 9 tests 통과 |
| `node scripts/toolchain.mjs typecheck` | 통과 |
| `node scripts/toolchain.mjs lint` | 통과 |
| `node scripts/toolchain.mjs build` | 통과 |
| `node scripts/toolchain.mjs test` | 7 files, 49 tests 통과 |
| `node scripts/toolchain.mjs test:e2e` | 2 files, 15 tests 통과 |
| `uv tool run --from uv==0.12.10 uv run --project docs --locked mkdocs build --strict` | 통과 |

focused test는 callback 오류+rollback 성공의 원래 오류 identity와 `rolled_back`, acquire 실패 시 release 없음,
callback을 호출하기 전 begin 실패 시 release, boundary와 release가 함께 실패할 때 기존 release 오류 우선순위,
commit 성공 뒤 release 실패의 `committed`, SQLite busy 번역, metrics 실패 격리를 확인합니다.
실제 `DatabaseMetrics`의 기록 실패가 성공 결과뿐 아니라 원래 callback 업무 오류도 덮지 않는지 확인합니다.
기존 실제 SQLite 시험은 deferred foreign-key COMMIT 실패, rollback 자체 실패 뒤 dirty worker 폐기,
lock timeout, worker 교체와 재시도를 그대로 통과했습니다.
DB-disabled 앱에는 `TransactionRunner`도 등록되지 않는 것을 lifecycle 시험으로 확인했습니다.

첫 전체 시험은 seed helper도 runner로 옮겨 business `committed` metric이 선행 증가하면서
실제 COMMIT 실패 검증 1개가 실패했습니다(6 files 통과, 1 file의 1/47 실패).
seed는 운영 요청의 business transaction outcome이 아닌 maintenance transaction이므로 기존 명시적 경계를 복원했고,
runner 적용 범위를 `ReservationsService` 업무 실행으로 좁혀 metric 의미와 기존 baseline을 보존했습니다.
실행 중인 서비스·컨테이너·공유 수집기, 다른 언어 구현, Prisma와 migration은 변경하거나 재검증하지 않았습니다.

## Task 11 검증 — 2026-09-15

`Connection`의 worker 응답 완료와 `sqlite.worker`의 query method 분기만 정리했습니다.
`Primary`는 검토 결과 pool 획득·timeout 번역·metrics·dirty cleanup·shutdown 책임이 이미 분명하여
변경하지 않았습니다. worker message shape과 close/death 처리, pending reject 순서와
`inTransaction` 갱신 시점은 유지했습니다.

`ts/nestjs/`에서 수행한 결과입니다.

| 명령 | 결과 |
| --- | --- |
| `node scripts/toolchain.mjs build` | 통과 |
| `node scripts/toolchain.mjs typecheck` | 통과 |
| `node scripts/toolchain.mjs lint` | 통과 |
| `node scripts/toolchain.mjs test` | 7 files, 49 tests 통과 |
| `node scripts/toolchain.mjs test:e2e` | 2 files, 15 tests 통과 |

기존 실제 SQLite 시험의 COMMIT·rollback 실패, dirty worker 폐기, worker 강제 종료와 원자성,
독립 프로세스 경합·복구를 다시 통과했습니다. 새 framework·RPC·ORM 변경이나 실행 중인
서비스·컨테이너 변경은 없었습니다.

## Task 12 검증 — 2026-09-16

`idempotency_keys.response`의 Drizzle 타입을 `unknown`으로 두고
`models/reservation-snapshot.ts`의 명시적 decoder/encoder를 통과한 값만 `Reservation`으로 만듭니다.
decoder는 필수 snake_case 필드 세 개, 비어 있지 않은 문자열 ID와 입력 문자열이 기존 Nest encoder의
`Date.toISOString()` milliseconds/`Z` 출력과 정확히 같은 실재 시각을 요구합니다. 따라서 숫자·null·배열,
누락 필드, 불가능한 날짜와 자동 정규화될 날짜 문자열을 거절하고 추가 저장 metadata는 무시하며,
기존 저장 형식은 그대로 encode합니다.

`ts/nestjs/`에서 고정 Node·pnpm wrapper로 수행한 결과입니다.

| 명령 | 결과 |
| --- | --- |
| `node scripts/toolchain.mjs exec vitest run test/unit/reservation-snapshot.spec.ts test/integration/reservations.spec.ts` | 2 files, 26 tests 통과 |
| `node scripts/toolchain.mjs format` | Prettier 실행 완료 |
| `node scripts/toolchain.mjs install --frozen-lockfile` | 통과, lockfile 변경 없음 |
| `node scripts/toolchain.mjs build` | 통과 |
| `node scripts/toolchain.mjs typecheck` | 통과 |
| `node scripts/toolchain.mjs lint` | 통과 |
| `node scripts/toolchain.mjs test` | 8 files, 64 tests 통과 |
| `node scripts/toolchain.mjs test:e2e` | 2 files, 15 tests 통과 |

새 unit 시험은 추가 metadata가 있는 정상 snapshot의 decode→encode 동일성과 필수 shape·필드 타입·빈 ID·
실재하지 않거나 기존 encoder의 canonical 형식이 아닌 시각의 거절을 확인합니다. 실제 SQLite integration 시험은 정상 예약 뒤 임시 fixture row만
각각 잘못된 shape·숫자 reservation ID·불가능한 날짜로 바꾸고 재생 요청이 500인지 확인했습니다.
세 경우 모두 성공/replayed header가 없고 재고 0·예약 1·멱등 키 1 상태를 유지하며,
기존 transaction runner에서 `rolled_back` 한 건으로 계측됩니다. 기존 정상 snapshot의 응답 본문 완전 동일 재생,
동일 키 충돌, rollback, worker 직렬화와 독립 프로세스 복구 시험도 전체 suite에서 다시 통과했습니다.
실행 중인 서비스·공유 DB·컨테이너·migration은 변경하지 않았고 시험은 OS 임시 SQLite 파일만 사용했습니다.

## 미검증 범위

실제 OS stdout 고장·디스크 장애·네트워크 파일시스템·PostgreSQL·운영 인증·외부 SDK·부하 p95/p99·비용은 미검증입니다.
예외 메시지·SQL·입력 원문은 공개하지 않으므로 상세 OS 원인 진단은 기본 로그만으로 보장하지 않습니다.
