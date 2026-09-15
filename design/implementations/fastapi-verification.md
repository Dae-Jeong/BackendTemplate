# FastAPI 검증 케이스

Status: SQLite 1차 구현·transactional decorator·typed snapshot·업무 validation 자동 검증 완료 · 아래 실행 결과와 후속 명세 구분 · 2026-09-16

[구현 설계](fastapi.md)의 상태와 경계를 검증합니다. 실행 결과 절은 실제 관측이며 이후 케이스 표는 검증 기준입니다.
진행 상태는 [단계별 task](fastapi-tasks.md), 실행 명령은 [사용 안내](../../python/fastapi/README.md)가 소유합니다.

## 예약 동시성·멱등성 실행 결과

확인일: 2026-09-08 · Task 6-3~8-2 및 마무리 리뷰.

| 검토 항목 | 실행 증거 |
| --- | --- |
| 자동 검사 | 전체 pytest **95개 통과**, Ruff lint/format·ty 통과. 기존 Starlette BlockingPortal deprecation 경고 1개 표시 유지 |
| schema | 공식 Alembic upgrade·반복 upgrade·check, 실제 파일 DB의 FK·음수 재고·키 중복 제약 검증 |
| 원자성 | 차감·예약·키 저장 중 실패 시 전체 rollback. 실제 예약 API에 지연 FK 위반을 주입해 commit 실패 시 500·변경 없음·같은 키 재시도 성공 검증 |
| 서로 다른 키 경합 | 독립 앱/Engine 2개에서 2개·12개 요청, 독립 프로세스 2개에서 재고 1개에 성공 하나 검증 |
| 같은 키 경합 | 12개 요청에서 신규 1개·재생 11개. 같은 키·다른 입력 경합은 성공 1개·409 충돌 1개 |
| 실패·복구 | SQLite 잠금과 pool timeout의 별도 503 및 회복, 저장 후 실패 재시도, 응답 body 유실 뒤 앱 재생성/재생 검증 |
| 프로세스 종료 | 별도 프로세스를 commit 직전/직후 `os._exit`로 종료하고 같은 키 재시도. 직전은 변경 없음, 직후는 저장된 결과 재생 |
| 시작 도구 | seed CLI 재실행 시 기존 재고를 채우거나 예약을 지우지 않는 시험 통과 |

컨테이너 이미지 빌드 후 `/app/data/reservations.db`에 migration·seed를 실행했습니다.
API·Prometheus·Grafana가 healthy이며 런타임 컨테이너의 `alembic check`는 변경 없음입니다.
실제 TCP 요청으로 첫 예약 201, 같은 키의 동일 본문 재생 201, 다른 입력 충돌 409를 확인했습니다.
별도 상품 `review-race-20260908`의 재고 1개에 12개 요청을 보내 201 하나·SOLD_OUT 409 열한 개를 확인했습니다.
SQLite를 읽기 전용으로 조회한 결과 해당 상품 재고 0·예약 1개, demo 재고 9·예약 1개, 전체 키 2개입니다.
Swagger `/docs` 200과 OpenAPI 예약 입력/응답 등록을 확인했습니다.

당시 세 outcome 계약의 동일 실행을 Prometheus와 대조해 `up=1`, 업무 트랜잭션 `committed=3`, `rolled_back=12`, `failed=0`,
종료 후 활성 Session·점유 연결 모두 0을 확인했습니다. commit 3건은 신규 예약 2건과 재생 1건입니다.
Grafana health는 200이며 실제 DB 화면에서도 UP·점유 0/상한 4·Session 0·commit 3·rollback 12·failed 0을 대조했습니다.
요청이 없는 최근 1분 p95는 No data로 표시됩니다. 기존 DB 패널의 추가 검증 범위는 아래에 기록합니다.

리뷰에서 오래된 미구현 상태 표기와 연결 획득 지표 설명을 수정했습니다.
연결 획득 지연에는 SQLite 쓰기 잠금 대기도 들어가며 순수 pool 대기 시간으로 해석하면 안 됩니다.
공통 DB 대역에 있던 commit 실패 시험을 실제 예약 API에도 추가해 검증 공백을 보완했습니다.

한계: readiness는 시작 연결·자원 준비 확인이며 schema revision 검사나 지속적인 DB 건강 확인은 아닙니다.
로컬 컨테이너는 아래 보완으로 migration을 선행하며 네이티브 실행은 사용 안내의 순서를 따릅니다. 임의 전원 장애·파일 손상·OOM의 무손실,
PostgreSQL 격리 수준/처리량·다중 worker HTTP 서버의 성능·운영 Sentry·인증/권한은 검증하지 않았습니다.
이 결과는 로컬 SQLite 1차 완료 판정이며 운영 서비스 전체 준비 완료를 뜻하지 않습니다.

## replay 조회 명명 검증 — 2026-09-15

Repository의 `find_matching_replay(session, key, product_id)`와 Service callsite만 변경했습니다.
`uv run --locked pytest tests/reservations/test_reservations.py`의 19개 시험으로 동일 입력 재생,
다른 입력 충돌, rollback 후 재시도, commit 전후 종료와 독립 연결·프로세스 경합을 확인했습니다.
전체 95개 시험과 `uv build`, Ruff check/format, ty도 통과했습니다. 기존 Starlette
`BlockingPortal` deprecation 경고 1개는 그대로 표시했습니다.
이 replay 명명 작업 당시에는 새 테스트·transaction 경계·replay repository를 추가하지 않았습니다.

## validation 책임 검증 — 2026-09-16

Repository의 과거 `find_matching_replay`·`get_product`·`decrease_stock` 책임을 각각 typed 저장 사실을 반환하는
`find_replay`·`find_product`·`decrease_stock_if_available`로 좁혔습니다. 순수 `validation/reservations.py`는
`ReplayRecord`와 `Product | None`만 소비하고 DB 호출·쓰기·transaction 없이 `IdempotencyConflict`와
`ProductNotFound`를 판정합니다. Service는 조건부 감소의 실제 실패 뒤 상품을 조회·검증한 다음 `SoldOut`을 발생시킵니다.

authoritative idempotency 행의 `product_id`를 snapshot 내부 `product_id`와 다르게 만든 API 회귀 시험에서,
요청과 snapshot이 같아도 409 `IDEMPOTENCY_CONFLICT`이고 재고·예약·키는 변하지 않음을 확인했습니다.
기존 API 시험이 replay·not-found·sold-out·seed와 상태 불변을 이미 검증하므로 validator 구현을 그대로 반복하는
별도 단위시험은 추가하지 않았습니다.

- `pytest -q tests/reservations/test_reservations.py`: 27개 통과.
- 전체 `pytest -q`: 109개 통과. 기존 Starlette `BlockingPortal` deprecation 경고 1개 표시 유지.
- Ruff check/format, ty, `uv build`: 모두 lock 환경의 공식 명령으로 통과.
- 모든 DB 시험은 pytest 임시 파일만 사용했으며 실행 중인 앱·사용자 DB는 변경하지 않았습니다.

## typed replay snapshot 경계 검증 — 2026-09-16

Repository 패턴과 `@transactional`은 유지하고, 저장된 멱등 응답 JSON을 기존 불변 `Reservation`의
`TypeAdapter`로 strict runtime validation한 뒤 반환하도록 변경했습니다. 쓰기는 Pydantic JSON mode를 사용하며
router도 `ReservationData.model_validate(..., from_attributes=True)`로 변환해 raw key 조립·접근을 제거했습니다.

실제 임시 SQLite와 API에서 새 snapshot의 UTC `Z` 저장, raw JSON의 기존 `+00:00` datetime 읽기와 최초 응답의
exact body replay를 확인했습니다. 필드 누락, 정수 `reservation_id`, null `product_id`, 숫자·null·불량 문자열
`created_at`은 모두 422나 성공이 아닌 500으로 거절되고 재고 0·예약 1개·키 1개의 기존 상태에 새 효과가 없었습니다.

- `pytest -q tests/reservations/test_reservations.py`: 26개 통과.
- 전체 `pytest -q`: 108개 통과. 기존 Starlette `BlockingPortal` deprecation 경고 1개 표시 유지.
- Ruff check/format, ty, `uv build`: 모두 통과.
- 기존 저장 실패·commit 실패 rollback, 응답 유실 후 replay, thread/process 경합 시험도 전체 suite에서 유지됐습니다.
- 모든 DB 시험은 pytest 임시 파일만 사용했으며 실행 중인 앱·사용자 DB를 변경하지 않았습니다.

## transactional decorator 검증 — 2026-09-15

두 독립 Python 앱에 각각 `core/transactions.py`를 추가하고 Service는 `@transactional`로 업무 범위만 표시했습니다.
dependency는 요청별 Session 생성·정리만 유지합니다. outcome은 `committed / failed`이며 `failed`는 rollback 완료를
주장하지 않습니다. pre-existing/autobegin transaction과 다른 Task의 중첩 거절은 decorator가 transaction을
시작하지 않았으므로 업무 transaction 지표에 포함하지 않습니다.

실제 임시 SQLite에서 같은 Session 중첩 성공의 commit/metric 1회, 잡힌 내부 실패의 rollback-only와 전체 원복,
잡히지 않은 업무 오류 identity, 사전 transaction 보존, 순차 재사용, commit/rollback 실패, 취소, pool timeout과
SQLite busy 번역, metrics 실패 시 성공 결과와 업무 오류 보존, 동시 Task 거절과 owner commit을 검증했습니다.
실제 FastAPI dependency의 요청별 Session/HTTP 500/cleanup도 유지했습니다. 수동 commit은 위반으로 감지하지만 이미
commit된 row는 남는다는 제한을 시험과 계약에 명시했습니다.

- FastAPI 기준선: 전체 pytest 101개 통과.
- FastAPI + FastCRUD: 전체 pytest 106개 통과. `commit=False`, audit·soft-delete·replay와 경합 시험 포함.
- 두 프로젝트 모두 Ruff check/format, ty, `uv build`를 lock 환경에서 실행했습니다.
- MkDocs strict build로 문서 링크와 Mermaid source를 검증했습니다.

모든 DB 시험은 pytest 임시 경로의 파일을 사용했습니다. 실행 중인 18092 앱과 `data/*.db`는 사용·변경·종료하지 않았습니다.

## 로컬 자동 migration 실행 결과

확인일: 2026-09-08. 컨테이너 기본 시작 명령을 `scripts/start.sh`로 연결했습니다.
이미지 빌드·shell 문법·Compose 설정 검사를 통과했습니다. 동일 이미지의 일회성 Compose 컨테이너에서
`/tmp`의 격리 DB로 다음을 확인했으며 시험 컨테이너는 `run --rm`으로 정리했습니다.

- 빈 DB에서 시작 명령만 실행해 Alembic head와 예약 테이블 생성 후 readiness 200.
- 상품 재고 7개를 저장한 뒤 같은 DB로 재시작해 재고 유지·readiness 200.
- DB URL 없이 시작해 readiness 200·예약 router 미등록.
- 존재하지 않는 revision을 가진 시험 DB에서 Alembic 오류 종료·API 시작 이벤트 없음.
- 정상 시작한 프로세스에 SIGTERM을 보내 `application.stopped`·`server.stopped` 확인.

실제 로컬 Compose 앱도 새 이미지로 시작해 API·Prometheus·Grafana healthy와 readiness 200을 확인했습니다.
기존 95개 pytest의 Python 업무 코드는 변경하지 않았으며 이번 검증은 이미지의 시작·실패·종료 경로를 대상으로 합니다.
계약과 흐름은 [로컬 컨테이너 migration 순서](fastapi.md#로컬-컨테이너-migration-순서)에 있습니다.

## DB 기반 실행 결과

확인일: 2026-09-08 · Task 6-1/6-2/6-2M. 예약·동시성·멱등성 업무 완료를 뜻하지 않습니다.

- Python 3.14.7 / SQLAlchemy 2.0.52 / aiosqlite 0.22.1. 전체 pytest 75개, Ruff lint/format, ty, uv build 통과.
- 파일 SQLite에서 transactional DDL rollback·foreign key 활성화·연결 무효화/회복·pool timeout·
  앱별 격리·시작 실패 dispose·Session 취소 정리·업무 중간 실패·commit/rollback 실패를 검증했습니다.
- 업무 취소 후 rollback 결과가 1건 기록되고 저장·활성 Session·점유 연결이 남지 않는 것을 확인했습니다.
- Compose API는 `/app/data` named volume에 UID 10001로 SQLite를 생성하고 ready가 되었습니다.
- 격리 시험 앱에서 점유 연결/활성 Session `0 → 1 → 0`, pool timeout `0 → 1`,
  업무 결과 `committed=1, rolled_back=1, failed=0`을 `/metrics`·Prometheus·Grafana에서 대조했습니다.
- 8개 DB 패널의 PromQL 실행·실제 PC 렌더링을 확인했습니다. 중단 시 DOWN/No data,
  DB 미설정 시 UP/DB No data를 구분합니다. DB 미설정 재시작 직후 과거 histogram이 보이지 않도록
  현재 DB pool 상한 지표의 존재도 확인합니다. p95는 bucket 기반 추정값입니다.
- 시험용 앱과 임시 DB를 종료·정리하고 Prometheus의 시험용 target을 제거했습니다.

재현은 `python/fastapi/`에서 아래 명령으로 시작합니다. 18082 포트가 비어 있는지 먼저 확인합니다.
시험 앱은 Docker 수집기가 접근하도록 `0.0.0.0:18082`에 bind하며 로컬 검증 동안만 실행합니다.
사용자 API에 시험 endpoint를 추가하지 않습니다.

```sh
uv tool run --from uv==0.12.10 uv run --locked python tests/manual_database_monitoring.py
# DB 미설정 화면 비교: 위 프로세스를 종료한 뒤 실행
uv tool run --from uv==0.12.10 uv run --locked python tests/manual_database_monitoring.py --without-db
```

검증 동안만 기존 `infra/monitoring/prometheus/prometheus.yml`의 `scrape_configs`에
`job_name: db-verification`, `static_configs: [{targets: [host.docker.internal:18082]}]`를 추가하고
`./scripts/compose.sh fastapi restart prometheus`로 반영합니다. Grafana의 DB 대시보드에서
수집 대상을 `db-verification`으로 선택합니다. 완료 후 Ctrl-C로 시험 앱을 종료하고 추가한 target을
제거한 뒤 Prometheus를 재시작합니다. 시험은 실제 사용자 앱·DB에 장애를 주입하지 않습니다.

## 초기화 케이스

| ID | 상황 | 통과 조건 |
| --- | --- | --- |
| INIT-01 | 정상 시작 | 설정 → logging → 앱 → lifespan 순서, 준비 전 ready=false입니다. |
| INIT-02 | 비밀 문자열을 포함한 불량 설정 | 자원 생성 0회·시작 실패·출력에 비밀값이 없습니다. |
| INIT-03 | logging 설정 두 번 | 소유 handler 1개·출력 1회이며 다른 도구 handler를 삭제하지 않습니다. |
| INIT-04 | 앱 두 개 | 설정·registry·override·readiness·서비스 문맥이 독립적입니다. |
| INIT-05 | 자원 A 획득 후 B 실패 | A 정리 1회·시작 실패·ready=false입니다. |
| INIT-06 | 종료 중 cleanup 오류 | 나머지 자원 정리를 시도하고 원래 실패를 보존합니다. |

## 요청 종료

| ID | 상황 | 통과 조건 |
| --- | --- | --- |
| END-01 | 200·422·404 | 실제 status와 완료 상태, 요약·counter·histogram 각 1회입니다. |
| END-02 | 응답 시작 전 업무 예외 | 500·오류 상세 1회·요약 1회이며 민감정보가 없습니다. |
| END-03 | 200 시작 후 body 오류 | status=200과 미완료를 보존하고 두 번째 response.start가 없습니다. |
| END-04 | 최종 body send의 OSError | send_failed이며 완료로 기록하지 않고 문맥을 복원합니다. |
| END-05 | await 중 task.cancel | 취소 전파·소유 자원 정리·문맥 복원·요약 1회입니다. |
| END-06 | receive에 disconnect | 이벤트를 그대로 전달하고 자동 취소·rollback을 가정하지 않습니다. |
| END-07 | 동시 요청 중 하나 취소 | 다른 요청은 완료되고 문맥·설정·결과가 섞이지 않습니다. |
| END-08 | logger 또는 metrics 오류 | 원래 응답·예외·취소와 문맥 정리를 보존합니다. 관측 누락은 별도 실패입니다. |
| END-09 | body 완료 이후 background 오류 | complete와 후속 error·body 완료 시 지연을 보존하며 재응답하지 않습니다. |
| END-10 | body 완료 없이 앱 반환 | incomplete이며 관측하지 않은 disconnect를 원인으로 추측하지 않습니다. |

## 기능·관측·복사

| 대상 | 통과 조건 |
| --- | --- |
| 인사 API | 입력 정규화·422·UTC 결과와 고정 clock DI 교체가 맞습니다. |
| 로그 | 유효한 한 줄 JSON·필드 타입·정수 ns·크기 제한·한글·줄바꿈·예약 키 충돌을 검사합니다. |
| 개인정보 | 합성 token·본문·예외 메시지·지역변수가 출력에 남지 않습니다. |
| metrics | 알려진 건수·결과·라벨 제한과 health/metrics 제외·앱별 분리를 검사합니다. |
| 복사형 시작점 | 개인 경로·다른 제품 의존 없이 설정·설치·실행·검증이 가능합니다. |
| Compose | 설정 검사·이미지 빌드·비 root·loopback·secret 제외·readiness를 검증합니다. |

fake ASGI receive/send와 제어 clock·Event barrier로 실패 시점을 고정합니다.
TestClient는 lifespan·HTTP 계약용이며 실제 TCP 종료를 증명하지 않습니다.
프로세스 logging·SIGTERM drain은 격리된 서버 프로세스로 별도 시험하고 외부 서비스·실제 DB를 사용하지 않습니다.
SIGKILL·OOM에서 cleanup·무손실을 보장하지 않습니다. 임의 sleep만으로 시험 성공을 판단하지 않습니다.

구현 순서는 초기화/격리 → 정상 요청 경로 → 실패/취소 → Compose/서버 종료 smoke 후보입니다.
구체적인 파일별 작업 계획과 명령은 구현 시작 시 작성합니다.
