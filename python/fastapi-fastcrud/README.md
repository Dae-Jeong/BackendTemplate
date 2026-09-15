# FastAPI + FastCRUD 시작점

기존 `python/fastapi/`와 분리된 uv 프로젝트입니다. 같은 HTTP·수명·관측·SQLite
예약 계약을 제공하되, 일반 조회·생성에 FastCRUD 0.22.3과 SQLAlchemy ORM mapped
class를 직접 사용합니다. 예약의 조건부 재고 차감은 명시적 SQLAlchemy
`update ... returning`으로 유지하며 `crud_router`와 Compose는 연결하지 않았습니다.

## 실행

이 디렉터리에서 실행합니다. Python 3.14.7과 의존성은 `.python-version`,
`pyproject.toml`, `uv.lock`에 고정되어 있습니다.

```sh
uv tool run --from uv==0.12.10 uv sync --locked
cp -n .env.example .env
mkdir -p data
```

`.env`의 `DB_PRIMARY_URL`을 이 앱 전용
`sqlite+aiosqlite:///./data/reservations.db`로 설정한 뒤 migration과 seed를 실행합니다.
seed는 기존 상품의 재고를 덮어쓰지 않습니다.

```sh
uv tool run --from uv==0.12.10 uv run --locked alembic upgrade head
uv tool run --from uv==0.12.10 uv run --locked python -m template_fastcrud_api.seed --product-id demo --stock 10
uv tool run --from uv==0.12.10 uv run --locked python -m template_fastcrud_api.run
```

기본 주소는 `127.0.0.1:18092`입니다. [Swagger](http://127.0.0.1:18092/docs)에서
인사와 예약 API를 실행하고, [readiness](http://127.0.0.1:18092/health/ready)와
[metrics](http://127.0.0.1:18092/metrics)를 확인할 수 있습니다. 종료는 Ctrl+C입니다.

`DB_PRIMARY_URL`을 비우면 DB 없는 인사·health·docs·metrics 앱으로 실행하며 예약
endpoint는 등록하지 않습니다. 실제 `.env`, `data/`, `.venv/`, `dist/`는
커밋하지 않습니다.

## 저장 경계

- `models/`: `DeclarativeBase`와 DB 제약
- `crud/`: model별 FastCRUD 객체와 조건부 재고 감소·seed upsert처럼 FastCRUD로 표현할 수 없는 SQL만 소유
- `services/`: `@transactional`로 원자 범위를 지정하고 FastCRUD를 직접 호출해 replay 판정 → 재고 차감 → reservation·replay 저장의 업무 순서를 표현
- `core/transactions.py`: `session.begin()`·SQLite `BEGIN IMMEDIATE` 획득·중첩 전파·오류 번역·계측
- `schemas/`: 기능별 파일에서 공개 HTTP schema와 FastCRUD 전용 Pydantic 입력·선택 schema를 구분해 소유

FastCRUD는 transaction을 소유하지 않습니다. 이 변형은 `Service → crud → DB`를 사용하며
FastCRUD를 다시 감싸는 forwarding Repository 함수나 범용 `BaseCRUD`를 두지 않습니다. HTTP
dependency는 Session 수명만 제공하고, decorated Service는 required keyword-only
`session`, `metrics`를 받습니다. 같은 Task·Session 중첩만 참여하며 수동 commit/rollback과
SAVEPOINT·REQUIRES_NEW는 지원하지 않습니다. 자동 `crud_router`는 인증·pagination·공개 응답 계약을 별도로 정한 뒤
추가할 수 있는 후속 데모입니다. 상세 범위는
[구현 설계](../../design/implementations/fastapi-fastcrud.md)를 봅니다.

FastCRUD 0.22.3의 create 입력은 `model_dump()`을 제공하는 Pydantic 모델입니다. Service가
storage 전용 Pydantic 입력을 만들고 `commit=False`로 호출하며, SDK create 계약은 test-local
입력 모델로 직접 검증합니다.

## 검증

```sh
uv tool run --from uv==0.12.10 uv run --locked ruff check .
uv tool run --from uv==0.12.10 uv run --locked ruff format --check .
uv tool run --from uv==0.12.10 uv run --locked ty check
uv tool run --from uv==0.12.10 uv run --locked pytest -q
uv tool run --from uv==0.12.10 uv build
```

테스트는 독립 임시 SQLite 파일을 사용하고 migration, rollback, commit 실패,
동시 thread/process 경합, 응답 유실 후 재생, FastCRUD flush/refresh와 ORM 비노출을
검증합니다. PostgreSQL·인증·운영 배포·Compose·자동 CRUD endpoint는 현재 범위가
아닙니다.
