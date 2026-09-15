# Rails 검증 기록

Status: Task 1~3 자동 검사·migration·네이티브 smoke 완료 · 2026-09-15

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
| `bin/rails test` | 25 runs, 72 assertions, 실패·오류·skip 0 |
| `bin/rubocop` | Task 3 포함 37 files, offense 0 |
| `bin/brakeman --no-pager -q` | error 0, security warning 0 |
| invalid `APP_ENVIRONMENT`의 `bin/rails runner` | 시작 실패, 입력 원문 없이 고정 오류 확인 |
| `.env.example` 복사 후 POSIX shell source | 공백 포함 `APP_NAME`과 `SERVER_PORT`를 오류 없이 로드 |
| `uv tool run --from uv==0.12.10 uv run --project docs --locked mkdocs build --strict` | build 성공, 누락 link/nav 경고 0 |

요청 시험은 이름 trim, 누락 `REQUIRED`, 공백 `TOO_SHORT`, `name[]=Marin`·`name[value]=Marin`의 `INVALID_TYPE`,
80자 초과 거절, 고정 UTC clock, live, 실제 SQLite ready,
주입한 DB 연결 실패의 ready 503, runtime settings 정상·실패를 포함합니다.

Task 3 요청 시험은 예약 생성/조회, 고정 UTC clock, malformed·누락·non-string·공백·too-long body,
unknown field 거절, invalid ID 422, not found 404, `Idempotency-Key` 미지원 422를 포함합니다. 예기치 않은 저장 실패는
성공 응답으로 바꾸지 않으며, Service 시험은 자동 test transaction을 끄고 별도 SQLite connection에서 commit된 row를 읽습니다.
또한 실제 insert 직후 제어된 예외를 발생시켜 transaction rollback 뒤 row count가 0인지 확인했습니다.

## Migration 검증

기존 development DB 대신 `/tmp`의 새 SQLite 경로를 `DB_PRIMARY_PATH`로 넘겨 `bin/rails db:migrate`를 실행했습니다.
예약 row를 넣은 뒤 같은 명령을 반복했을 때 적용할 migration이 없는 no-op이었고 row 1개가 보존됐습니다.
생성된 `db/schema.rb`는 Rails 표준 schema dump이며 table, unique index, NOT NULL과 두 CHECK constraint를 기록합니다.

별도 test process에는 서로 다른 외부 `DB_PRIMARY_PATH`와 `DATABASE_URL`을 함께 넣고 `db:test:prepare`와 전체 시험을 실행했습니다.
resolved database는 계속 `storage/test.sqlite3`였고 외부 후보 파일은 생성되지 않았습니다.

## 중앙 리뷰 회귀 검증

test database는 `config/database.yml`의 명시적 `sqlite3:` URL로 `storage/test.sqlite3`에 고정했습니다.
별도 Rails test process에 `DB_PRIMARY_PATH=storage/shared-must-not-be-used.sqlite3`와 같은 파일을 가리키는
`DATABASE_URL`을 동시에 전달해도 실제 resolved database가 `storage/test.sqlite3`이고 공유 후보 파일은 생성되지 않음을 검증했습니다.

Rails query parser가 배열과 object로 만드는 두 `name` 형태는 모두 500 없이 422 Problem 응답으로 끝납니다.
누락과 공백은 각각 `REQUIRED`, `TOO_SHORT`로 구분했습니다. `.env.example`은 `APP_NAME`을 quote하고,
README의 `cp -n .env.example .env`와 `set -a; . ./.env; set +a`를 앱 디렉터리에서 그대로 실행해 로드한 뒤 시험 `.env`를 제거했습니다.

## 실제 native boot

Task 3 smoke도 실행 직전에 18088과 향후 Docker host 18089가 LISTEN 중이 아님을 `lsof`로 확인하고,
격리 SQLite 경로에 migration을 먼저 적용했습니다.

```sh
RAILS_ENV=development APP_ENVIRONMENT=local \
DB_PRIMARY_PATH=/tmp/backend-template-rails-task3.r3s4JD/native-smoke.sqlite3 bin/rails db:migrate
APP_ENVIRONMENT=local SERVER_HOST=127.0.0.1 SERVER_PORT=18088 \
DB_PRIMARY_PATH=/tmp/backend-template-rails-task3.r3s4JD/native-smoke.sqlite3 ./bin/start
```

Puma PID 29964가 `127.0.0.1:18088`에서 Ruby 4.0.6 / Rails 8.1.3.1로 시작했습니다.
실제 TCP 응답은 예약 POST 201과 같은 ID의 GET 200, greeting/live/ready 200이었습니다. 응답의 공개 ID는
32자리 소문자 hex이고 `created_at`은 `Z` UTC였습니다. Ctrl+C 후 graceful shutdown, 18088 port 해제,
기존 18080/18081/18083/18084/18086/18090/19090/13000 listener 유지를 확인했습니다.

## 제약

Dockerfile은 생성 후 내부 3000, 향후 host 18089, 비 root, production SQLite 경로를 검토했지만 사용자 범위에 따라
image build와 container 실행은 하지 않았습니다. root Compose·script·문서 메뉴·공통 포트 표도 변경하지 않았습니다.
products/stock, 동시성·멱등성, metrics, 전체 Problem/404/405/500, 부하와 운영 배포는 미검증 후속 범위입니다.
