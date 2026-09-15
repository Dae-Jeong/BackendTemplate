# Rails 단계별 Task

Status: Task 1~4 및 예약 업무 검증 책임 정리 완료 · 2026-09-16

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

## Task 4. 재고 원자성

- [x] products table, 공개 ID unique와 `stock >= 0` DB CHECK 추가
- [x] 기존 reservations의 임의 `product_id`를 보존하고 FK를 추가하지 않는 upgrade 경계 확정
- [x] 명시적이고 반복 안전하며 기존 재고를 reset하지 않는 `bin/rails db:seed` 추가
- [x] Service transaction의 첫 DB 작업으로 `stock > 0` 조건부 UPDATE 후 예약 INSERT
- [x] 상품 없음 404, 품절 409, SQLite busy와 pool timeout 503 구분
- [x] 실제 INSERT 실패 rollback, raw DB CHECK, 독립 process 경합, fresh/upgrade/repeated migration·seed 검증
- [x] native 18088에서 재고 소진과 오류 응답 smoke 검증

## 다음 작은 Task

Task 5는 멱등 key 저장·동일 요청 결과 재생을 이번에 확인한 원자적 재고 흐름에 붙이는 단계입니다. 인증, metrics, 전체 Problem handler,
Compose는 각자의 작은 Task로 유지합니다.

## ProductId 책임 정리

- [x] 순수 `ProductId.normalize(value)`가 String trim과 128자 상한, 네 입력 오류 reason을 소유
- [x] ReservationService는 `ProductId::Invalid`만 기존 `InvalidInput`으로 번역
- [x] Product와 Reservation validation이 `ProductId::MAX_LENGTH`를 공유하고 자동 strip callback은 추가하지 않음
- [x] migration은 유지하고 model·Service·HTTP·CLI 입력 경계 차이를 보존
- [x] 새 규칙 단위시험과 전체 SQLite stock·rollback·경합·HTTP 회귀 검증

이 책임 정리는 위의 예약 멱등성 Task 5를 구현한 것이 아닙니다.

## 예약 업무 검증 책임 정리

목표:
Active Record 조회와 transaction 순서는 Service에 유지하면서 제품·예약 존재라는 순수 업무 조건을 별도 validation에 둡니다.

예상 결과:

- `ReservationValidation`이 DB 호출 없이 제품 존재 boolean과 조회된 예약 존재를 검사함
- Service가 `ProductId.normalize`, 실제 조건부 차감 실패 뒤 `SoldOut`, transaction과 DB 오류 번역을 계속 소유함
- 제품·예약 미존재 오류가 Service에 종속되지 않은 feature module에 있고 controller가 같은 오류를 변환함
- Active Record model validation, `Data` 결과, 실제 조건부 stock SQL과 기존 HTTP·rollback·경합 계약이 유지됨

결과:

- `ReservationErrors`에는 별도 빈 Base 없이 `ProductNotFound`와 `NotFound`만 두고 validation과 controller가 공유합니다.
- Service는 `Product.exists_by_product_id?`와 `Reservation.find_by` 결과를 순수 validation에 전달하며 `SoldOut`은 계속 Service에서 발생시킵니다.
- 입력 정규화, model validation, seed, idempotency 미지원 범위, migration과 SQL은 변경하지 않았습니다.
- 공식 bundle 검사에서 전체 44 runs·147 assertions와 RuboCop 46 files가 통과했습니다.
