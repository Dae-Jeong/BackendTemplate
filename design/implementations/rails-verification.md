# Rails 검증 기록

Status: Task 1~4 및 예약 업무 검증 책임 정리 자동 검사 완료 · 2026-09-16

## 도구와 생성 명령

실제 사용 버전은 Ruby 4.0.6, RubyGems 4.0.16, Bundler 4.0.16, Rails 8.1.3.1,
Puma 8.0.2, sqlite3 gem 2.9.6입니다. ruby-build v20260716을
`/Users/marin/.cache/backend-template-rails/` 아래에 설치해 Ruby를 source build했고 global 설정은 바꾸지 않았습니다.

`rails new --help`와 `bin/rails generate controller --help`를 먼저 확인했습니다. 실제 scaffold 핵심 명령은 다음입니다.

```sh
rails _8.1.3.1_ new ruby/rails --name=BackendTemplateRails --api --database=sqlite3 \
  --skip-git --skip-bundle --skip-action-mailer --skip-action-mailbox --skip-action-text \
  --skip-active-storage --skip-action-cable --skip-jbuilder --skip-solid --skip-kamal --skip-ci --no-rc
bin/rails generate controller v1/greetings show --skip-routes
bin/rails generate controller health live ready --skip-routes
bin/rails generate model Reservation 'reservation_id:string{32}:uniq' 'product_id:string{128}' --skip-fixture
bin/rails generate controller v1/reservations create show --skip-routes
bin/rails generate model Product 'product_id:string{128}:uniq' stock:integer --skip-fixture
```

`--skip-git`으로 nested `.git` 생성을 막았습니다. 기능에 필요 없는 mail, storage, cable, Solid adapters와 Kamal은 생성 범위에서 제외했고,
API mode의 Active Record, controller, Puma, Minitest 관례는 유지했습니다.

Ruby 4.0.6 환경에서 lockfile이 선택했던 `json 3.0.2`는 정상 JSON POST도
`JSON.parse: wrong number of arguments (given 2, expected 1)`로 실패했습니다. Rails 8.1.3.1의 로컬
`ActiveSupport::JSON.decode`가 options hash를 두 번째 positional argument로 넘기는 반면 json 3은 keyword-only이기 때문입니다.
`bundle add --help` 확인 뒤 `bundle add json --version '~> 2.0'`으로 지원 CLI를 사용해 Gemfile과 lockfile을
`json 2.21.2`로 고정했고, 정상·malformed JSON 요청을 다시 검증했습니다. parser monkey patch는 추가하지 않았습니다.

## 자동 검증

`ruby/rails/`에서 프로젝트 전용 Ruby를 PATH 앞에 둔 뒤 실행했습니다.

| 명령 | 실제 결과 |
| --- | --- |
| `bundle install` / `bundle check` | lock 생성·설치 완료, dependencies satisfied |
| `bundle lock --add-platform aarch64-linux x86_64-linux` | Docker 대상 Linux platform을 lockfile에 기록 |
| `bin/rails zeitwerk:check` | `All is good!` |
| `bin/rails test` | 39 runs, 137 assertions, 실패·오류·skip 0 |
| `bin/rubocop` | Task 4 포함 42 files, offense 0 |
| `bin/brakeman --no-pager -q` | error 0, security warning 0 |
| invalid `APP_ENVIRONMENT`의 `bin/rails runner` | 시작 실패, 입력 원문 없이 고정 오류 확인 |
| `.env.example` 복사 후 POSIX shell source | 공백 포함 `APP_NAME`과 `SERVER_PORT`를 오류 없이 로드 |
| `uv tool run --from uv==0.12.10 uv run --project docs --locked mkdocs build --strict` | build 성공, 누락 link/nav 경고 0 |

## ProductId 책임 정리 검증

새 `ProductIdTest` 5 runs는 trim 반환, 정확히 128자 허용과 nil·비문자열·공백·129자의
`REQUIRED`·`INVALID_TYPE`·`TOO_SHORT`·`TOO_LONG` reason을 확인합니다. 영향 범위의 model·Service·HTTP
시험은 28 runs, 86 assertions가 통과했고 전체는 44 runs, 147 assertions, 실패·오류·skip 0입니다.

`Product`와 `Reservation`은 `ProductId::MAX_LENGTH`를 공유하지만 model 저장값을 자동 trim하지 않습니다.
HTTP 예약은 Service가 정규화 오류만 기존 `InvalidInput`으로 번역하고, CLI seed는 기존 model 경계를 유지합니다.
기존 Service 대역은 더 이상 `Reservation`의 product ID 상수를 복제하지 않습니다. 전체 시험으로 실제 SQLite
commit/rollback·busy, stock 차감과 독립 process 경합을 재검증했습니다.

프로젝트 전용 Ruby 4.0.6에서 bundle check, Zeitwerk, 전체 test, RuboCop 44 files와
Brakeman error/security warning 0을 확인했습니다. migration·callback·dependency 변경은 없습니다.

## 예약 업무 검증 책임 정리 검증

`ReservationServiceTest`는 제품 미존재 `ReservationErrors::ProductNotFound`와 실제 Service의 stock 차감·INSERT rollback·
SQLite busy·pool timeout을 확인합니다. controller 시험은 없는 예약의 `ReservationErrors::NotFound`가 기존
404 `RESERVATION_NOT_FOUND`로 변환됨을 실제 route에서 확인합니다.

프로젝트 전용 Ruby 4.0.6와 Bundler 4.0.16을 `PATH`에만 적용해 README의 공식 명령을 실행했습니다.

```sh
bundle check
bin/rails zeitwerk:check
bin/rails test
bin/rubocop
```

최종 결과는 dependency 충족, Zeitwerk `All is good!`, **44 runs·147 assertions·실패/오류/skip 0**,
RuboCop **46 files·offense 0**입니다. 외부 DB 환경을 쓰지 않는 기존 test 설정과 격리 SQLite만 사용했고
migration·dependency·Compose·멱등성·metrics는 변경하지 않았습니다.

요청 시험은 이름 trim, 누락 `REQUIRED`, 공백 `TOO_SHORT`, `name[]=Marin`·`name[value]=Marin`의 `INVALID_TYPE`,
80자 초과 거절, 고정 UTC clock, live, 실제 SQLite ready,
주입한 DB 연결 실패의 ready 503, runtime settings 정상·실패를 포함합니다.

Task 3 요청 시험은 예약 생성/조회, 고정 UTC clock, malformed·누락·non-string·공백·too-long body,
unknown field 거절, invalid ID 422, not found 404, `Idempotency-Key` 미지원 422를 포함합니다. 예기치 않은 저장 실패는
성공 응답으로 바꾸지 않으며, Service 시험은 자동 test transaction을 끄고 별도 SQLite connection에서 commit된 row를 읽습니다.
또한 실제 insert 직후 제어된 예외를 발생시켜 transaction rollback 뒤 row count가 0인지 확인했습니다.

Task 4는 정상 생성의 재고 1 차감, 상품 없음 404 `PRODUCT_NOT_FOUND`, 품절 409 `SOLD_OUT`, 실패 시 예약 없음,
raw INSERT의 음수 재고 CHECK 거절을 확인합니다. 예약 INSERT는 실제 unique violation을 일으켜 같은 transaction에서 먼저 차감한
재고가 원복되는지 확인했습니다. 별도 SQLite 연결이 `BEGIN IMMEDIATE` write lock을 가진 상태에서 Active Record busy handler를
50ms로 제한한 실제 lock 시험은 `DatabaseBusy`로 끝났고 stock 2·예약 0을 유지했습니다. pool timeout은 실제 pool 고갈 실측이
아니라 `ActiveRecord::ConnectionTimeoutError` 번역과 cause 보존 시험이며 HTTP의 두 timeout은 각각 503 공개 코드와
`Retry-After: 1`을 확인했습니다.

독립 process 경합 시험은 `/tmp` 격리 SQLite를 migration한 뒤 stock 3에 Rails runner process 6개를 barrier로 동시에 출발시켰습니다.
모든 process는 별도 boot·connection을 사용하고 30초 timeout 안에 join했습니다. 결과는 성공 3, `SOLD_OUT` 3,
`DATABASE_BUSY` 0, 다른 오류 0이며 저장 예약 3, 남은 stock 0으로 초과 예약이 없었습니다. spawn 중간 실패와 timeout cleanup도
이미 시작한 process를 TERM 후 2초 상한, 필요 시 KILL하고 reap합니다.

## Migration 검증

Task 4 시험은 `/tmp`의 fresh SQLite에 migration을 두 번 실행해 reservations와 products table, stock CHECK를 확인했습니다.
upgrade는 실제 `VERSION=20260915043127 bin/rails db:migrate`로 Task 3 schema까지만 만든 뒤 `legacy / arbitrary product` 예약을
삽입하고 최신 migration을 두 번 실행했습니다. legacy row는 그대로 남고 products에 inventory를 추정해 backfill하지 않았습니다.
`bin/rails db:seed` 실행, stock 3으로 변경, seed 재실행 뒤에도 3이 유지되어 기존 재고를 reset하지 않음을 확인했습니다.
생성된 `db/schema.rb`는 Rails 표준 schema dump이며 products 공개 ID unique, NOT NULL과 product ID·음수 재고 CHECK를 기록합니다.

별도 test process에는 서로 다른 외부 `DB_PRIMARY_PATH`와 `DATABASE_URL`을 함께 넣고 `db:test:prepare`와 전체 시험을 실행했습니다.
resolved database는 계속 `storage/test.sqlite3`였고 외부 후보 파일은 생성되지 않았습니다.

## 중앙 리뷰 회귀 검증

test database는 `config/database.yml`의 명시적 `sqlite3:` URL로 `storage/test.sqlite3`에 고정했습니다.
별도 Rails test process에 `DB_PRIMARY_PATH=storage/shared-must-not-be-used.sqlite3`와 같은 파일을 가리키는
`DATABASE_URL`을 동시에 전달해도 실제 resolved database가 `storage/test.sqlite3`이고 공유 후보 파일은 생성되지 않음을 검증했습니다.
Task 4 전체 39개 test도 서로 다른 `/tmp` sentinel 두 경로를 `DB_PRIMARY_PATH`와 `DATABASE_URL`로 동시에 설정해 실행했고,
두 외부 파일이 생성되지 않았습니다. migration·경합 test가 띄우는 development 자식 process는 `DATABASE_URL`을 명시적으로
unset하고 각 test가 만든 `/tmp`의 `DB_PRIMARY_PATH`만 사용합니다.

Rails query parser가 배열과 object로 만드는 두 `name` 형태는 모두 500 없이 422 Problem 응답으로 끝납니다.
누락과 공백은 각각 `REQUIRED`, `TOO_SHORT`로 구분했습니다. `.env.example`은 `APP_NAME`을 quote하고,
README의 `cp -n .env.example .env`와 `set -a; . ./.env; set +a`를 앱 디렉터리에서 그대로 실행해 로드한 뒤 시험 `.env`를 제거했습니다.

## 실제 native boot

Task 4 smoke는 실행 직전에 18088이 LISTEN 중이 아님을 `lsof`로 확인하고,
격리 SQLite 경로에 migration을 먼저 적용했습니다.

```sh
RAILS_ENV=development APP_ENVIRONMENT=local \
DB_PRIMARY_PATH=/tmp/backend-template-rails-task4.C0cvVY/native-smoke.sqlite3 bin/rails db:migrate
RAILS_ENV=development APP_ENVIRONMENT=local \
DB_PRIMARY_PATH=/tmp/backend-template-rails-task4.C0cvVY/native-smoke.sqlite3 bin/rails db:seed
APP_ENVIRONMENT=local SERVER_HOST=127.0.0.1 SERVER_PORT=18088 \
DB_PRIMARY_PATH=/tmp/backend-template-rails-task4.C0cvVY/native-smoke.sqlite3 ./bin/start
```

Puma PID 90765가 `127.0.0.1:18088`에서 Ruby 4.0.6 / Rails 8.1.3.1로 시작했습니다. smoke용 stock을 1로 만든 뒤
실제 TCP POST는 201 한 번, 다음 요청은 409 `SOLD_OUT`, 없는 상품은 404 `PRODUCT_NOT_FOUND`였습니다. DB에는 stock 0과
예약 1개만 남았습니다. Ctrl+C 후 graceful shutdown과 18088 port 해제를 확인했습니다.

## 제약

Dockerfile은 생성 후 내부 3000, 향후 host 18089, 비 root, production SQLite 경로를 검토했지만 사용자 범위에 따라
image build와 container 실행은 하지 않았습니다. root Compose·script·문서 메뉴·공통 포트 표도 변경하지 않았습니다.
SQLite 경합은 단일 host의 독립 process로 검증했으며 PostgreSQL 동시성이나 처리량을 검증한 것이 아닙니다. 실제 pool 고갈,
멱등성, metrics, 전체 Problem/404/405/500, 부하와 운영 배포는 미검증 후속 범위입니다.
