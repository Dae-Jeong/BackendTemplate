# Rails 폴더 구조와 책임

Status: Task 1~2 실제 구조 · 2026-09-15

`ruby/rails/`는 Rails generator의 관용적 역할별 경로를 유지합니다.

```text
app/
  controllers/application_controller.rb
  controllers/health_controller.rb
  controllers/v1/greetings_controller.rb
  models/application_record.rb
  models/greeting.rb
  services/greeting_service.rb
config/
  application.rb
  database.yml
  puma.rb
  routes.rb
  runtime_settings.rb
test/
  controllers/health_controller_test.rb
  controllers/v1/greetings_controller_test.rb
  models/database_configuration_test.rb
  models/runtime_settings_test.rb
```

| 경로 | 책임 |
| --- | --- |
| `controllers/v1/greetings_controller.rb` | query 입력, service 호출, data/Problem HTTP 변환 |
| `controllers/health_controller.rb` | liveness와 주입된 DB readiness check의 HTTP 상태 변환 |
| `models/greeting.rb` | HTTP와 ORM에서 분리된 인사 결과 값 |
| `models/application_record.rb` | 향후 실제 Active Record 모델의 Rails 표준 상위 클래스 |
| `services/greeting_service.rb` | 이름 정규화·제약과 주입받은 clock으로 결과 생성 |
| `config/application.rb` | runtime settings, UTC clock, readiness callable 조립 |
| `config/runtime_settings.rb` | env 파싱과 안전한 시작 검증 |
| `config/database.yml` | 환경별 SQLite 파일·pool·busy timeout, test의 외부 DB env 차단 |
| `test/` | 실제 route 요청, query 타입, clock/DB 대체, DB 파일 격리, 설정 실패 검증 |

단순 greeting에는 Active Record 모델을 만들지 않았고 `Greeting`도 DB entity가 아닙니다.
예약 저장이 추가될 때 실제 table을 소유하는 모델과 migration을 함께 추가하고, controller는 그 entity를 직접 serialize하지 않습니다.
여러 저장 순서와 transaction 경계가 생길 때만 `app/services`에 해당 업무 service를 추가합니다.
