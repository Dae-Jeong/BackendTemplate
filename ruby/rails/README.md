# Rails 시작점

Status: Task 1~4 재고 예약 API·네이티브 검증 완료 · 2026-09-15

Ruby 4.0.6, Rails 8.1.3.1, Active Record와 SQLite를 사용하는 독립 API 앱입니다.
`.ruby-version`, `Gemfile`, `Gemfile.lock`이 도구와 gem 버전을 고정합니다. 시스템 Ruby나
사용자 기본 shell 설정을 바꾸지 말고 `.ruby-version`을 지원하는 version manager 또는 프로젝트 전용 Ruby를 사용합니다.

## Ruby 준비

1. [Ruby 공식 설치 안내](https://www.ruby-lang.org/en/documentation/installation/)에서 OS에 맞는 사용자 로컬 설치 방식이나 version manager를 선택합니다.
2. [Ruby 4.0.6 공식 release](https://www.ruby-lang.org/en/news/2026/07/14/ruby-4-0-6-released/)와 `.ruby-version`에 맞춰 Ruby 4.0.6을 설치합니다. 시스템 Ruby를 교체하거나 global 기본 버전을 바꾸지 않습니다.
3. 이 디렉터리에서 `ruby --version`이 `ruby 4.0.6`, `bundle --version`이 lockfile의 Bundler 4.0.16인지 확인합니다.

현재 머신에서 사용한 ruby-build와 cache의 실제 경로는 재현 증거이므로
[검증 기록](../../design/implementations/rails-verification.md)에만 기록합니다. 다른 사용자는 같은 절대 경로를 만들 필요가 없습니다.

## 의존성 설치와 네이티브 실행

이 디렉터리에서 실행합니다. Bundler 설치 위치는 Git에서 제외되는 프로젝트의 `vendor/bundle`로 지정합니다.

```sh
bundle config set --local path vendor/bundle
bundle install
bundle check
cp -n .env.example .env
set -a
. ./.env
set +a
bin/rails db:migrate
bin/rails db:seed
./bin/start
```

`.env`는 shell에서 명시적으로 읽습니다. Rails 앱은 env 파일을 자동으로 읽지 않습니다.
기본 listener는 `127.0.0.1:18088`이며 실행 직전에 점유 여부를 확인합니다. 종료는 Ctrl+C입니다.

```sh
curl -fsS 'http://127.0.0.1:18088/v1/greetings?name=Marin'
curl -fsS -X POST http://127.0.0.1:18088/v1/reservations \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"product-1"}'
curl -fsS http://127.0.0.1:18088/v1/reservations/{reservation_id}
curl -fsS http://127.0.0.1:18088/health/live
curl -fsS http://127.0.0.1:18088/health/ready
```

- `GET /v1/greetings`: String `name`을 trim한 뒤 1~80자로 검증하고 `data.message`, UTC `data.generated_at`을 반환합니다. 누락은 `REQUIRED`, 공백만 있으면 `TOO_SHORT`, 배열·객체 query는 `INVALID_TYPE` 422입니다.
- `POST /v1/reservations`: JSON body의 String `product_id`를 trim해 1~128자로 검증하고 재고 한 단위를 조건부 차감한 뒤 예약을 저장합니다. 성공은 `data.reservation_id`, `data.product_id`, UTC `data.created_at`을 201로 반환합니다. 상품 없음은 404 `PRODUCT_NOT_FOUND`, 재고 없음은 409 `SOLD_OUT`이며 둘 다 예약을 만들지 않습니다.
- `GET /v1/reservations/:reservation_id`: 32자리 소문자 hex ID를 검증하고 저장한 예약을 반환합니다. 형식 오류는 422, 없는 예약은 404입니다.
- `GET /health/live`: 프로세스 생존을 `{"status":"alive"}`로 반환합니다.
- `GET /health/ready`: Active Record의 현재 SQLite 연결에 `SELECT 1`을 실행하고 성공 시 ready, 연결 실패 시 503을 반환합니다.

## 검사

```sh
bundle check
bin/rails zeitwerk:check
bin/rails test
bin/rubocop
```

실제 실행 결과와 로컬 도구 설치 방식은 [검증 기록](../../design/implementations/rails-verification.md)에 있습니다.

## 데이터와 컨테이너 경계

개발·시험·production은 기본적으로 `storage/development.sqlite3`, `storage/test.sqlite3`,
`storage/production.sqlite3`를 각각 사용합니다. 개발·production은 `DB_PRIMARY_PATH`로 격리 파일을 지정할 수 있지만,
test는 안전을 위해 `DB_PRIMARY_PATH`와 Rails의 `DATABASE_URL`을 모두 무시하고 항상 `storage/test.sqlite3`를 사용합니다.
현재 인사 응답의 `Greeting`과 예약 응답의 `ReservationResult`는 일반 Ruby 값 객체이므로 Active Record entity를 HTTP에 노출하지 않습니다.
앱 시작은 migration을 자동 실행하지 않습니다. 새 DB나 schema 변경 뒤에는 위처럼 `bin/rails db:migrate`를 먼저 실행합니다.
seed도 boot에서 자동 실행하지 않습니다. `bin/rails db:seed`를 명시적으로 실행하면 `product-1`을 재고 10으로 최초 한 번만 만들며,
이미 존재하는 상품의 현재 재고는 다시 10으로 설정하지 않습니다.

예약 생성은 같은 Active Record transaction에서 `stock > 0` 조건부 UPDATE와 INSERT를 수행합니다. 기존 Task 3 예약의 임의
`product_id` text를 보존하기 위해 `reservations.product_id`에는 의도적으로 products FK를 추가하지 않았습니다. 따라서 새 생성 경로의
상품 존재·재고 보장은 Service가 담당하지만, legacy row나 DB 직접 쓰기가 products row를 참조한다고 보장하지는 않습니다.
인증과 멱등 결과 재생은 아직 제공하지 않습니다. `Idempotency-Key`가 오면 구현된 것처럼 무시하지 않고
`IDEMPOTENCY_NOT_SUPPORTED` 422로 거절합니다.

SQLite 잠금 timeout은 503 `DATABASE_BUSY`, Active Record pool 획득 timeout은 503 `DATABASE_POOL_TIMEOUT`과
`Retry-After: 1`로 구분합니다. 예약 쓰기는 비멱등이므로 서버가 자동 재시도하지 않으며, 현재는 응답 유실 뒤 같은 요청의
중복 효과를 막을 key가 없습니다.

Dockerfile은 Ruby 4.0.6, 내부 포트 3000, 비 root 실행, production SQLite 경로를 정의합니다.
향후 로컬 게시 포트는 `127.0.0.1:18089`이지만 이번 작업에서는 이미지를 빌드하거나 컨테이너를 배포하지 않았습니다.
멱등성, metrics·중앙화된 전체 Problem 처리·Compose 통합은 후속 Task입니다.
