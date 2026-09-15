# Rails 시작점

Status: Task 1~2 최소 API 앱 구현·네이티브 검증 완료 · 2026-09-15

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
./bin/start
```

`.env`는 shell에서 명시적으로 읽습니다. Rails 앱은 env 파일을 자동으로 읽지 않습니다.
기본 listener는 `127.0.0.1:18088`이며 실행 직전에 점유 여부를 확인합니다. 종료는 Ctrl+C입니다.

```sh
curl -fsS 'http://127.0.0.1:18088/v1/greetings?name=Marin'
curl -fsS http://127.0.0.1:18088/health/live
curl -fsS http://127.0.0.1:18088/health/ready
```

- `GET /v1/greetings`: String `name`을 trim한 뒤 1~80자로 검증하고 `data.message`, UTC `data.generated_at`을 반환합니다. 누락은 `REQUIRED`, 공백만 있으면 `TOO_SHORT`, 배열·객체 query는 `INVALID_TYPE` 422입니다.
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
현재 인사 응답의 `Greeting`은 일반 Ruby 값 객체이므로 Active Record entity를 HTTP에 노출하지 않습니다.

Dockerfile은 Ruby 4.0.6, 내부 포트 3000, 비 root 실행, production SQLite 경로를 정의합니다.
향후 로컬 게시 포트는 `127.0.0.1:18089`이지만 이번 작업에서는 이미지를 빌드하거나 컨테이너를 배포하지 않았습니다.
예약·migration·metrics·중앙화된 전체 Problem 처리·Compose 통합은 후속 Task입니다.
