# Rails 구현 설계

Status: Task 1~3 최소 저장 API·네이티브 검증 완료 · 2026-09-15

## 버전 선택

Ruby 4.0.6과 Rails 8.1.3.1을 고정했습니다. 2026-09-15 기준 Ruby 공식 release 목록의 최신 stable은
[Ruby 4.0.6](https://www.ruby-lang.org/en/downloads/releases/)이고, Rails 공식 release 목록과 RubyGems의 최신 non-yanked gem은
[Rails 8.1.3.1](https://rubygems.org/gems/rails/versions)입니다. 로컬 gemspec에서 Rails 8.1.3.1의 Ruby 요구사항
`>= 3.2.0`을 확인했고 이 조합으로 bundle, eager load, 요청 시험과 실제 boot를 통과했습니다.
Rails 8.1은 2026-10-10까지 bug fix, 2027-10-10까지 security fix 지원 대상이라는
[공식 maintenance 안내](https://rubyonrails.org/2025/10/29/new-rails-releases-and-end-of-support-announcement)도 선택 근거입니다.

Ruby는 ruby-build v20260716으로 홈의 이 저장소 전용 cache에 설치했습니다. 시스템 Ruby, Homebrew Ruby,
global gem account와 shell 기본 설정은 변경하지 않았습니다. 앱 자체는 `.ruby-version`, Gemfile의 `ruby`, Docker build argument에
같은 Ruby 버전을 기록하고 Rails는 Gemfile과 lockfile에서 고정합니다.

## Active Record 저장 흐름

```mermaid
sequenceDiagram
    participant C as ReservationsController
    participant S as ReservationService
    participant M as Reservation model
    participant AR as Active Record adapter/pool
    participant DB as SQLite
    C->>S: create(product_id, clock)
    S->>AR: Reservation.transaction
    AR->>DB: BEGIN
    S->>M: create!(fields + UTC time)
    M->>AR: validated INSERT
    AR->>DB: INSERT
    AR->>DB: COMMIT
    S->>M: to_result
    M-->>S: ReservationResult
    S-->>C: plain Ruby value
    C-->>C: data JSON + 201
```

`Reservation < ApplicationRecord`는 Rails 관례로 `reservations` table에 매핑됩니다. model이 field 제약과
`ReservationResult` 매핑을 소유하고 controller는 model을 직접 JSON으로 만들지 않습니다. `ReservationService`가 명시적인
transaction block을 소유하며 Repository wrapper나 요청 전체 자동 transaction은 추가하지 않았습니다.

Zeitwerk는 파일 경로와 상수명을 맞춰 `app/models/reservation_result.rb`의 `ReservationResult`,
`app/services/reservation_service.rb`의 `ReservationService`를 필요할 때 autoload합니다. 요청은 Service를 호출하고,
Active Record adapter/pool이 현재 요청 thread의 SQLite connection 획득·반납과 SQL 변환을 관리합니다.

transaction block이 정상 반환되어야 Active Record가 commit합니다. block 안에서 만든 결과를 HTTP에 먼저 내보낼 수는 없지만,
코드상 성공 시점을 흐리므로 저장된 model만 block 밖으로 가져오고 `to_result`는 commit 뒤 호출합니다. insert 뒤 예외가 나면
block이 빠져나오기 전에 rollback되어 결과와 성공 응답이 생성되지 않습니다. clock은 기존 `config.x.clock` callable을
controller가 Service에 명시적으로 전달하고 Service가 한 번 호출해 UTC `created_at`과 `updated_at`에 사용합니다.

## 설정과 수명

`RuntimeSettings.from_env`가 앱 boot 중 app name, 환경, bind host와 port를 검증하며 입력 원문을 오류에 넣지 않습니다.
Puma thread 수, Active Record pool 수, SQLite busy timeout은 각각 별도 env입니다. 실제 listener bind는 Puma가
`SERVER_HOST`와 `SERVER_PORT`를 사용합니다.

Active Record와 Rails request executor가 connection pool의 획득·반납과 프로세스 수명을 소유합니다.
readiness는 현재 연결에서 실제 `SELECT 1`을 실행하지만 schema revision이나 장기적인 DB 건강을 보장하지 않습니다.
liveness는 DB를 조회하지 않습니다. test 연결은 명시적인 `sqlite3:` URL로 `storage/test.sqlite3`에 고정해
`DB_PRIMARY_PATH`와 Rails의 자동 `DATABASE_URL` merge가 개발·공유 DB를 가리키지 못하게 합니다.
앱 boot가 migration을 숨겨 실행하지 않으며 native 실행 전에 `bin/rails db:migrate`를 명시적으로 실행합니다.

## 현재와 후속 범위

현재 예약은 `product_id` text를 저장하고 생성/조회하는 학습용 중간 API입니다. products table, 재고 차감,
동시 예약 보호, 멱등 저장·재생, 인증은 없습니다. `Idempotency-Key`는 무시하지 않고 미지원 422로 거절합니다.
metrics, 공통 404/405/500을 포함한 전체 Problem 처리, 관측과 Compose 연결도 후속 Task가 소유합니다.
