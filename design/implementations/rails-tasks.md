# Rails 단계별 Task

Status: Task 1~3 완료 · 2026-09-15

## Task 1. 실행 방식과 저장 경계

- [x] 공식 release와 local gemspec으로 Ruby 4.0.6 / Rails 8.1.3.1 호환 확인
- [x] 시스템 기본값을 바꾸지 않는 프로젝트 전용 Ruby·gem·bundle cache 사용
- [x] `.ruby-version`, Gemfile, Gemfile.lock, Docker build argument에 버전 고정
- [x] Rails 관용 경로와 callable 기반 clock/readiness dependency 선택
- [x] 개발·시험·production SQLite 파일 분리와 test의 `DB_PRIMARY_PATH`·`DATABASE_URL` 상속 차단

## Task 2. 가장 작은 앱 실행

- [x] 실제 `rails new --help` 확인 후 `rails new --api --database=sqlite3 --skip-git` 기반 생성
- [x] controller generator help 확인 후 greeting/health controller 생성
- [x] `GET /v1/greetings`, `/health/live`, `/health/ready` 구현
- [x] 이름 누락·공백·배열·객체 query, data envelope, UTC clock 대체, DB readiness 실패 요청 시험
- [x] `.env.example`, native start, Dockerfile, README 작성
- [x] locked bundle, Zeitwerk, tests, RuboCop, 설정 실패와 native TCP smoke 검증
- [x] Rails 문서를 MkDocs hook·nav·watch에 연결하고 strict build 검증

## Task 3. 최소 예약 저장

- [x] model/controller generator help 확인 뒤 예약 model·migration·controller 생성
- [x] `POST /v1/reservations`, `GET /v1/reservations/:reservation_id`와 32자리 hex 공개 ID 구현
- [x] model/DB 제약, 명시적 Service transaction, commit 뒤 일반 Ruby 결과 변환
- [x] body 형식·field·path ID의 422와 없는 예약 404 정책 구현
- [x] 실제 SQLite 별도 연결 commit 확인과 post-insert 예외 rollback 시험
- [x] fresh/repeated migration, data 보존, test DB env 격리, native 18088 smoke 검증

## 다음 작은 Task

Task 4는 products/stock schema와 조건부 재고 차감으로 동시 초과 예약을 막고 실제 경합 시험을 추가하는 단계입니다.
멱등 key 저장·동일 요청 결과 재생은 그 원자성이 확인된 뒤 별도 단계로 붙입니다. 인증, metrics, 전체 Problem handler,
Compose는 각자의 작은 Task로 유지합니다.
