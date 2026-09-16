# Backend Template — NestJS

NestJS·Express·SQLite 예약 예제입니다. 생성자 DI, 명시적 HTTP DTO, Problem Details,
앱별 JSON 로그·Prometheus registry, 단일 Primary와 주입 가능한 transaction runner,
commit 뒤 성공 응답을 제공합니다.

문서 지도: [구현 색인](../../design/implementations/README.md) ·
[설계](../../design/implementations/nestjs.md) · [구조](../../design/implementations/nestjs-structure.md) ·
[Task](../../design/implementations/nestjs-tasks.md) · [검증](../../design/implementations/nestjs-verification.md) ·
[루트 README](../../README.md) · [적용 Runbook](../../RUNBOOK.md)

2026-09-16: 저장된 멱등 JSON의 runtime 검증 경계와 손상 row HTTP 회귀를 포함해 typecheck·lint·build,
unit/실제 DB/프로세스 시험 64개와 HTTP e2e 15개를 통과했습니다.
2026-09-15: `TransactionRunner.run<T>()` 책임 분리와 focused 회귀를 포함해 typecheck·lint·build,
unit/실제 DB/프로세스 시험 49개와 HTTP e2e 15개를 통과했습니다.
2026-09-08: build·typecheck·lint, unit/실제 DB/프로세스 시험 40개와 HTTP 시험 15개를
통과했습니다. 네이티브 18083의 실제 DB 예약·재생과 새 디렉터리의 locked 설치·빌드·migration·예약도 확인했습니다.
컨테이너 예약·재시작 재생과 공유 Prometheus·Grafana 수집도 확인했습니다.

## DB 없는 앱 실행

이 디렉터리에서 실행합니다. 로컬 `node`와 `npm`이 필요하며 wrapper는 전역 도구를 바꾸지 않고
`.node-version`의 Node와 `package.json`의 `packageManager`를 npm 실행 캐시에 준비합니다.

```sh
node scripts/toolchain.mjs install --frozen-lockfile
node scripts/toolchain.mjs build
node scripts/toolchain.mjs start:prod
```

`http://127.0.0.1:18083/health/ready`는 `{"status":"ready"}`입니다.
DB가 없을 때에도 인사·health·docs·metrics를 사용할 수 있습니다.
예약 라우트·OpenAPI 항목·DB provider는 등록하지 않으므로 예약 경로는 404입니다.
종료는 Ctrl+C입니다. 기존 포트가 사용 중이면 해당 프로세스를 종료하지 말고 배정을 확인합니다.

## SQLite 예약 실행

파일 DB 경로를 명시합니다. migration과 seed는 별도 CLI이며 기존 상품을 seed해도 재고를 덮어쓰지 않습니다.
`.env.example`은 설정 목록이고 자동으로 읽지 않습니다. 아래처럼 shell 환경을 전달합니다.

```sh
mkdir -p data
export DB_PRIMARY_URL=file:./data/template.db
node scripts/toolchain.mjs db:migrate
node scripts/toolchain.mjs db:seed widget 1
node scripts/toolchain.mjs start:prod
```

```sh
curl -i http://127.0.0.1:18083/v1/reservations \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: example-1' \
  -d '{"product_id":"widget"}'
```

첫 응답은 201과 `Idempotency-Replayed: false`입니다. 같은 키·입력을 재전송하면
동일한 `data`와 201, `Idempotency-Replayed: true`를 반환합니다.
다른 입력은 409 `IDEMPOTENCY_CONFLICT`, 남은 재고 없는 새 키는 409 `SOLD_OUT`입니다.
성공 `data`는 `reservation_id`, `product_id`, UTC `created_at`만 포함합니다.

| 경로 | 의미 |
| --- | --- |
| `GET /` | `data.message = Hello, NestJS!` |
| `GET /v1/greetings?name=Marin` | 인사와 UTC 생성 시각 |
| `POST /v1/reservations` | 한 개 예약, `Idempotency-Key` 필수 |
| `GET /health/live`, `GET /health/ready` | envelope 없는 health |
| `GET /metrics` | Prometheus text, 관측 실패 시 503 |
| `GET /docs`, `GET /openapi.json` | Swagger UI와 OpenAPI |

## 설정

| 환경 변수 | 기본값·조건 |
| --- | --- |
| `APP_NAME`, `SERVICE_VERSION`, `APP_ENVIRONMENT` | `backend-template-nestjs`, `0.0.1`, `local` |
| `SERVER_HOST`, `SERVER_PORT` | `127.0.0.1`, `18083` |
| `LOG_LEVEL` | `info`; `debug`, `warn`, `error`, `silent` 지원 |
| `SHUTDOWN_TIMEOUT_SECONDS` | 10; 이후 HTTP socket을 닫되 진행 중 DB 작업은 확정·정리를 기다립니다. |
| `DB_PRIMARY_URL` | 공백이면 비활성; `file:./data/template.db` 또는 `file:/app/data/template.db` |
| `DB_POOL_SIZE` | 2; worker/연결 상한, 지연 생성, 최대 8 |
| `DB_POOL_TIMEOUT_MS`, `DB_BUSY_TIMEOUT_MS` | 각각 1000; 연결 획득과 SQLite 잠금 대기는 다른 503 코드입니다. |

`better-sqlite3`는 동기 드라이버입니다. HTTP 이벤트 루프는 이를 직접 호출하지 않으며,
전용 worker의 SQLite 실행을 Drizzle `sqlite-proxy` callback으로 기다립니다.
하나의 transaction lease는 같은 worker 연결을 사용합니다. DB 파일·WAL·SHM은 같은 writable 디렉터리에 둡니다.
다른 프로세스·앱도 같은 파일을 쓸 수 있지만 네트워크 파일시스템은 검증하지 않았습니다.

## 기능 추가와 검증

`controllers/` → `services/` → `repositories/` 흐름입니다. DTO는 `dto/`, 내부 readonly 값은
`contracts/`, 저장 schema는 `models/`에서 소유합니다. AppModule 하나에서 생성자 의존성을 조립합니다.
새 Controller·Service는 `node scripts/toolchain.mjs exec nest generate --help`로 현재 CLI 옵션을 확인한 뒤
역할 경로와 `--flat --no-spec`을 사용합니다. 시험은 `test/`에 둡니다.
schema 변경은 `db:generate --name 변경명`으로 생성된 SQL·snapshot을 검토하고 `db:migrate`로 적용합니다.
현재 405 경계는 공개 OpenAPI의 정적 경로를 사용하므로 매개변수 경로를 추가할 때는 메서드 매칭 시험도 추가합니다.
HTTP 관측은 공개 Express `req.route.path`를 사용하며, 서로 다른 ID가 같은 경로 template 라벨로 집계됨을 시험했습니다.

```sh
node scripts/toolchain.mjs install --frozen-lockfile
node scripts/toolchain.mjs build
node scripts/toolchain.mjs typecheck
node scripts/toolchain.mjs test
node scripts/toolchain.mjs test:e2e
node scripts/toolchain.mjs lint
```

실제 DB 시험의 worker는 `dist/database/sqlite.worker.js`를 실행하므로 **시험 전에 build**합니다.
시험은 OS 임시 포트·임시 파일만 사용합니다. `drizzle-kit`의 이전 esbuild-kit 하위 패키지 deprecation
경고는 남아 있지만 stable CLI 동작을 확인했습니다. `@scarf/scarf` 설치 telemetry는 실행하지 않습니다.

## 컨테이너 실행

저장소 루트에서 실행합니다.

```sh
export DB_PRIMARY_URL=file:/app/data/template.db
./scripts/compose.sh nestjs up --build --wait api
./scripts/compose.sh nestjs exec -T api pnpm db:seed widget 1
```

[Swagger](http://127.0.0.1:18084/docs)에서 예약을 호출하거나 위 curl의 포트를 18084로 바꿉니다.
종료는 `./scripts/compose.sh nestjs stop api`이며 데이터는 유지됩니다.
공유 수집기는 [로컬 모니터링](../../design/implementations/local-monitoring.md)을 따릅니다.

Docker context는 `ts/nestjs`, `NODE_VERSION` build arg는 `.node-version`에서 중앙 Compose가 전달합니다.
pnpm은 `packageManager`에서 읽습니다. 내부 포트 3000, 게시 `127.0.0.1:18084`, non-root UID/GID 10001,
데이터 경로 `/app/data`를 사용합니다. writable volume은 중앙에서 연결합니다.

`scripts/start.sh`는 `DB_PRIMARY_URL`이 있으면 공식 Drizzle migration CLI를 실행한 뒤 Node로 exec합니다.
이미지에는 이 CLI의 실행 의존성과 pnpm을 포함합니다. seed 명령은 컨테이너 안에서
`pnpm db:seed widget 1`이며 운영 자동 seed는 하지 않습니다.
별도 Compose·수집기·PostgreSQL 인스턴스는 만들지 않습니다.

PostgreSQL·인증·원격 DB·운영 계정·외부 수집 SDK·부하 p95/p99·비용 보장은 후속입니다.
DB 드라이버를 바꾸면 schema·migration·트랜잭션 경합·복구 시험을 새 DB에서 다시 수행해야 합니다.
