# Rails 폴더 구조와 책임

Status: Task 1~3 실제 구조 · 2026-09-15

`ruby/rails/`는 Rails generator의 관용적 역할별 경로를 유지합니다.

```text
app/
  controllers/application_controller.rb
  controllers/health_controller.rb
  controllers/v1/greetings_controller.rb
  controllers/v1/reservations_controller.rb
  models/application_record.rb
  models/greeting.rb
  models/reservation.rb
  models/reservation_result.rb
  services/greeting_service.rb
  services/reservation_service.rb
config/
  application.rb
  database.yml
  puma.rb
  routes.rb
  runtime_settings.rb
db/
  migrate/*_create_reservations.rb
  schema.rb
test/
  controllers/health_controller_test.rb
  controllers/v1/greetings_controller_test.rb
  controllers/v1/reservations_controller_test.rb
  models/database_configuration_test.rb
  models/reservation_test.rb
  models/runtime_settings_test.rb
  services/reservation_service_test.rb
```

| 경로 | 책임 |
| --- | --- |
| `controllers/v1/greetings_controller.rb` | query 입력, service 호출, data/Problem HTTP 변환 |
| `controllers/health_controller.rb` | liveness와 주입된 DB readiness check의 HTTP 상태 변환 |
| `controllers/v1/reservations_controller.rb` | JSON/path 입력 검증 정책, service 호출, 일반 Ruby 결과의 data/Problem HTTP 변환 |
| `models/greeting.rb` | HTTP와 ORM에서 분리된 인사 결과 값 |
| `models/application_record.rb` | Active Record 모델의 Rails 표준 상위 클래스 |
| `models/reservation.rb` | `reservations` table 매핑, field 제약, `ReservationResult` 변환 |
| `models/reservation_result.rb` | HTTP·Active Record에서 분리된 예약 결과 값 |
| `services/greeting_service.rb` | 이름 정규화·제약과 주입받은 clock으로 결과 생성 |
| `services/reservation_service.rb` | 예약 생성 transaction과 commit 뒤 결과 생성, ID 조회 |
| `config/application.rb` | runtime settings, UTC clock, readiness callable 조립 |
| `config/runtime_settings.rb` | env 파싱과 안전한 시작 검증 |
| `config/database.yml` | 환경별 SQLite 파일·pool·busy timeout, test의 외부 DB env 차단 |
| `db/migrate`, `db/schema.rb` | 예약 table의 변경 이력과 Rails 표준 현재 schema |
| `test/` | 실제 route 요청, 실제 SQLite commit/rollback, model 제약, clock/DB 대체, DB 파일 격리 검증 |

단순 greeting에는 Active Record 모델을 만들지 않았고 `Greeting`도 DB entity가 아닙니다.
예약은 실제 table을 소유하므로 모델과 migration을 함께 두되 controller는 entity를 직접 serialize하지 않습니다.
단일 insert라도 commit 성공과 공개 응답의 경계를 드러내기 위해 예약 Service가 transaction을 소유합니다.
