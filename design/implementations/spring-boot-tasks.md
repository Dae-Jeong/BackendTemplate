# Spring Boot 단계별 구현 task

Status: Task 1–11 구현·자동 시험 완료 · reservation 저장·replay 명명 정리 · 2026-09-15

실행 명령은 [사용 가이드](../../java/spring-boot/README.md), 시험 결과·미검증은
[검증 기록](spring-boot-verification.md)이 소유합니다.

| Task | 구현 결과 | 검증 |
| --- | --- | --- |
| 0 구조 설계 | 역할별 package·constructor DI·MVC·단일 Primary | design 정본 대조 |
| 1 생성·빌드 | Initializr API, Boot 4.1.1, Wrapper 9.7.1, .java-version 25, strict lock | clean test bootJar·Docker build |
| 2 DI·인사 | Clock Bean·순수 Greeting·HTTP DTO 분리 | GreetingServiceTest·실제 HTTP |
| 3 설정·수명·오류 | 빈 URL 자동 DB 비활성, 설정 검증, Problem·404/405·입력422 | LifecycleTest·HttpDatabaseTest·ShutdownTest |
| 4 로그·metrics·실행 | ECS JSON, MDC·async 완료, Micrometer, OpenAPI, native·Docker | ObservationTest·SpecialHttpTest·native18085 |
| 5 DB 선택 | 사용자 선택 H2, JdbcClient·Hikari·Flyway | file DB·공식 CLI migration 생성·MigrationTest |
| 6 Primary·예약 | public Service transaction·key claim·재고 UPDATE·결과 저장 | rollback·commit실패·재시도·독립 연결 |
| 7 경합·멱등·복구 | 키별 충돌 복구·독립 상품 진행·TCP 프로세스 경합·embedded 재시작 | HttpDatabaseTest·ProcessRecoveryTest·TransactionFailureTest |
| 8 사용 가이드 | 복사 후 빌드·DB 비활성/활성·seed·API 추가 안내 | README 명령·복사 검증 및 중앙 통합 기록 참조 |
| 9 JPA 전환 | Boot 관리 JPA·Hibernate, 기존 H2 schema·계약 보존 | strict clean test bootJar, 34개·11 suites·실패 0 |
| 10 코드 읽기 비용 개선 | Problem 직접 생성·입력 의미 명시·예약 전용 오류 분기 제거·claim 판별명·표현 정리 | strict clean test bootJar, 35개·11 suites·실패 0 |
| 11 reservation 저장·replay 명명 | paired reservation/replay 저장과 입력 일치 replay 조회를 메서드 이름에 명시 | 기존 strict clean test bootJar |

## 단계별 commit

- `27305d3`: 공식 Initializr 생성 결과 보존, 최초 Java 21 빌드.
- `2d745e0`: Java 25·HTTP 계약·최초 H2 예약·실제 HTTP/file DB 시험.
- `a65cb26`: 중앙 리뷰의 전역 guard 제거·자동 no-db·Java 단일 정본·실패/프로세스/관측 검증,
  clean 시험 27개 통과.
  후속 오류 번역 수정과 통합 결과는 검증 기록에서 확인합니다.

V1의 초기 guard는 V2 migration에서 제거합니다. 과거 migration을 지우거나 덮어쓰지 않고
기존 예약·재생 결과를 보존한 업그레이드를 시험했습니다.
공통 실행·수집·문서 메뉴는 main에 통합했습니다.

## Task 9. Spring Data JPA·Hibernate 전환

목표:
Java 구현의 JdbcClient 저장 경계를 JPA entity·Spring Data repository로 전환하고 기존 H2 데이터·HTTP·transaction 계약을 보존합니다.

예상 결과:
- 승인 설계가 spring-boot.md에 기록되고 Flyway V1/V2 변경 없이 schema validate가 동작함.
- 단일 JpaTransactionManager·public Service 경계·실제 완료 metrics와 좁은 claim 충돌 복구가 구현됨.
- stale entity·flush/commit 실패 rollback·unique race·기존 데이터·no-db 시험 및 strict locked clean test bootJar가 통과함.
- Spring 사용/구조/검증 문서에 실제 결과와 중앙 Docker·수집 검증의 남은 범위가 기록됨.

결과:

- `4301427` 승인 설계, `6025aaf` 구현·시험. 기존 V1/V2 migration 수정은 없습니다.
- EntityManager persist·Spring Data 조회/조건부 JPQL·VARCHAR UTC mapping, 단일 JpaTransactionManager가 구현됐습니다.
- JPA flush 경합·stale entity·batch FK 순서·전체 rollback·commit 실패·rollback 응답 실패·no-db·schema mismatch·기존 nanosecond HTTP 재생을 확인했습니다.
- `./gradlew clean test bootJar --no-daemon --console=plain`이 34개·11 suites·실패/오류/skip 0으로 통과했습니다.
- 사용·구조·설계·검증 문서와 공통 구현 표를 갱신했습니다. Docker 18086의 기존 H2 데이터 보존·재시작 재생·동시 HTTP·Prometheus 수집도 통과했습니다.
- 최종 통합 증거는 [JPA 로컬 통합 검증](spring-boot-verification.md#jpa-로컬-통합-검증)에 있습니다.

## Task 10. 계약을 유지하는 코드 정리

목표: HTTP·transaction·DB·관측 계약을 유지하면서 불필요한 중간 객체와 불명확한 호출을 줄입니다.

결과:
- `ApiExceptionHandler.problem()`은 공개 Problem을 직접 만들고 request ID를 한 번 조회합니다. HTTP status와 업무 code의 이름을 구분했습니다.
- 예약 필드 오류는 기존 deserializer의 `InvalidInput`으로 표현하며 공통 handler의 예약 전용 DatabindException 분기를 제거했습니다.
- `Inputs.text`·`Inputs.token`, 응답 지역 변수, 명시적 import와 일관된 분기·접근자·들여쓰기로 읽기 비용을 줄였습니다.
- `isH2ClaimInsertConflict()`는 기존 H2 SQLState와 INSERT SQL 조건을 그대로 사용합니다. transaction·flush·FK·시각·완료 metrics 동작은 유지합니다.
- 누락·null·숫자·boolean·배열·객체·unknown field·잘못된 JSON의 공개 422 location/code 회귀 시험을 추가했습니다. 전체 명령과 결과는 [Task 10 검증](spring-boot-verification.md#task-10-코드-정리-검증)에 있습니다.
- 중앙 코드 검토를 완료했습니다. 실행 중인 서비스·공유 DB·Compose는 변경하지 않았으며 이번 코드 정리에는 컨테이너 재배포를 포함하지 않습니다.

## Task 11. reservation 저장·replay 명명

`ReservationRepository.save`를 `saveReservationAndReplay`로, `replay`를
`findMatchingReplay`로 바꾸고 `ReservationService` callsite를 함께 변경했습니다.
paired persist·flush와 key/product mismatch 판단은 기존 repository에 남겼고,
transaction proxy·rollback 뒤 `ReservationAttempts`의 fresh read 경계는 변경하지 않았습니다.
이름 변경을 복제하는 새 테스트 없이 기존 전체 Spring 시험으로 검증했습니다.
