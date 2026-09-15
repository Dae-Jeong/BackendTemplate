# Rails 단계별 Task

Status: Task 1~2 완료 · 2026-09-15

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

## 다음 작은 Task

Task 3은 예약 schema 하나와 migration을 공식 Rails generator로 추가하고, 명시적인 Active Record transaction 안에서
저장 성공 뒤에만 외부 응답 값을 만드는 단계입니다. unique 제약·조건부 재고 차감·멱등 결과 재생을 한꺼번에 넣기 전에
단일 생성/조회와 rollback 요청 시험부터 통과시킵니다. Docker build, Compose, metrics와 전체 Problem 처리는 이 단계에 섞지 않습니다.
