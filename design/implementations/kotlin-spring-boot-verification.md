# Kotlin Spring Boot 검증 기록

Status: **Task 1–10 구현·독립 검토·자동 시험·native 재시작·문서 통합 검증 완료** · 2026-09-16

이 기록은 Kotlin 구현 baseline `10f6367`, 공유 가이드 통합 `8dd7127`, 그리고 그 위에 반영한 Task 9 독립 검토 변경을 대상으로 합니다.
공통 계약의 근거는 [Java 검증 기록](spring-boot-verification.md), Kotlin 고유 선택은
[구현 설계](kotlin-spring-boot.md)를 봅니다. Compose·container는 실행하지 않았습니다.

## 생성과 빌드

공식 Spring Initializr API의 `type=gradle-project-kotlin`, `language=kotlin`, `bootVersion=4.1.1`,
`javaVersion=25`, package `com.backendtemplate`, MVC/JPA/Flyway/H2/validation/actuator 입력으로 생성했습니다.
생성된 Kotlin 2.3.21, Boot 4.1.1, Wrapper 9.7.1 조합을 유지했습니다. H2 console은 제거했고
Springdoc 3.1.1, Prometheus, strict dependency lock과 Kotlin warnings-as-errors를 적용했습니다.

이 머신의 기본 `java`는 21이므로 전역 설정을 바꾸지 않고 아래 JDK 25를 해당 명령에만 전달했습니다.

```sh
env JAVA_HOME=/opt/homebrew/opt/openjdk@25 \
  PATH=/opt/homebrew/opt/openjdk@25/bin:/usr/bin:/bin:/usr/sbin:/sbin \
  ./gradlew clean test bootJar --no-daemon --console=plain
```

Task 9 수정 뒤 결과: 57초, 9 tasks 실행, `BUILD SUCCESSFUL`. `compileJava`는 `NO-SOURCE`였고
Kotlin compiler warning은 0개였습니다. XML 집계는 13 suites·38 tests, failure/error/skip 0입니다.
생성된 `gradle.lockfile`로 strict resolution이 적용됐고 BootJar는 안정 경로 `build/libs/app.jar`로 생성됐습니다.

## 자동 시험

총 38개·13 suites, failure/error/skip 0입니다. Java 구현의 기존 35개 시나리오는
`src/test/java`에 복사해 Kotlin getter·nullable return callsite만 적응했고, production compatibility API는 추가하지 않았습니다.

| suite | 수 | 실제 범위 |
| --- | ---: | --- |
| HttpDatabaseTest | 11 | exact HTTP/Problem, strict input, replay/conflict, stock race, key race, lock/pool timeout, isolation, lost response, proxy seed |
| TransactionFailureTest | 6 | commit/begin/rollback/constraint 실패, checked·unchecked rollback, metrics outcome |
| LifecycleTest | 4 | no-db, schema mismatch, invalid config, partial startup pool close |
| ProcessRecoveryTest | 4 | embedded restart, 두 JVM key/stock 경쟁, commit 전후 process death |
| JpaPersistenceTest | 3 | flush/clear stale entity, FK batch rollback, claim flush race |
| 나머지 기존 Java suites | 7 | migration, shutdown, observation, special HTTP, greeting, context |
| KotlinPersistenceBoundaryTest | 2 | 실제 Kotlin proxy rollback, nullable miss, entity openness/no-arg와 Hibernate lazy load |
| KotlinJsonBoundaryTest | 1 | missing/null/number/malformed JSON 422와 OpenAPI snake_case schema |

테스트 transaction 자동 rollback에 기대지 않고 임시 H2 file, 독립 JDBC connection과 실제 JVM/process를 사용했습니다.
기존 시험을 삭제·skip하거나 기대값을 완화하지 않았습니다. Kotlin `ProductRepository.findById`는 `ProductEntity?`이고
Java harness가 `Optional`을 요구하지 않도록 test callsite를 바꿨습니다.

## native no-db와 file DB 재시작

실행 전에 `lsof -nP -iTCP:18093 -sTCP:LISTEN`으로 미점유를 확인했습니다.
Task 9에서는 빌드한 JAR를 `./scripts/start.sh`로 loopback 18093에서 DB URL 없이 실행해 다음을 확인했습니다.

- `/health/ready` 200, `{"status":"ready"}`
- `/v1/greetings?name=Marin` 200과 typed `data` body
- `POST /v1/reservations` 404
- 종료 뒤 18093 listener 없음

독립 임시 경로 `/tmp/kotlin-task9.MmUTw3/template`에 `./scripts/start.sh --seed`로 stock 2를 seed한 뒤
같은 script로 서버를 실행했습니다. key `task9-native-replay`의 첫 요청은 201,
`Idempotency-Replayed: false`와 아래 저장 결과를 반환했습니다.

```json
{"data":{"reservation_id":"0d400b9057914bcaa2eb506838f8a8a5","product_id":"demo","created_at":"2026-09-15T17:42:40.692384Z"}}
```

SIGINT로 소유 process를 종료하고 같은 file로 `./scripts/start.sh`를 다시 실행한 뒤 동일 요청을 보냈습니다.
두 번째 응답은 201, `Idempotency-Replayed: true`였고 body byte가 첫 응답과 같았습니다.
마지막 JVM도 종료했고 18093 listener가 없음을 확인했으며 기존 18090·18092 서비스에는 접근하지 않았습니다.

## Task 9 독립 검토와 수정

기존 구현자가 아닌 reviewer가 production 46 Kotlin files 전체와 resources, Java 35개 harness의 파일별 diff,
Kotlin 고유 3개 시험을 설계·구조·Task 기준과 대조했습니다. 수정 뒤 미해결 high-impact 항목은 0개입니다.

| 우선순위 | 발견 위치 | 판정과 수정 |
| --- | --- | --- |
| 중간 | `scripts/start.sh:4`, `build.gradle.kts` | version이 들어간 JAR 경로가 release 변경에 취약했습니다. BootJar를 `app.jar`로 고정하고 script·사용 안내·native smoke를 같은 경로로 통일했습니다. |
| 중간 | `http/RequestContextFilter.kt:34` | 관측용 오류 표시와 동일 instance 재던지기가 네 catch에 중복됐습니다. 단일 `Throwable` catch로 합치고 기존 async/finally/MDC 완료 흐름을 보존했습니다. |
| 낮음 | `observation/TransactionMetrics.kt:14` | 완료 outcome이 임의 `String`이고 `Started`의 boolean 인자가 모호했습니다. private `Outcome` enum을 만들고 exporter tag 경계에서만 문자열로 변환했으며 named argument를 사용했습니다. |
| 낮음 | `KotlinJsonBoundaryTest.kt:17` | 중첩 `Pair`가 body/location/code 의미를 숨겼습니다. test-local `JsonCase`로 이름을 부여했고 검증 사례와 기대값은 유지했습니다. |
| 낮음 | `kotlin-spring-boot-structure.md:12` | 구조 문서가 존재하지 않는 `BackendTemplateApplication`을 표시했습니다. 실제 `TemplateApplication.kt`와 class 이름으로 고쳤습니다. |

비수정 판정도 함께 확인했습니다. `DatabaseEnvironment`의 map은 Spring의 동적 property source이지 업무 데이터가 아니며,
`IdempotencyClaimed`는 공개 업무 오류가 아니라 claim INSERT의 H2 23505만 repository 경계에서 분류해 rollback 뒤 fresh read를 요청하는
내부 복구 신호입니다. Service가 제품 존재·품절·replay product 정책을 계속 결정하고 Repository는 commit이나 공개 Problem을 소유하지 않습니다.
`ReservationService.replay`의 내부 불변조건 오류 메시지는 공개 응답·구조화 로그로 노출되지 않고 500 safe contract로 변환됩니다.

## Task 10 공용 문서 통합

루트 README, Runbook, 구현 index와 MkDocs nav를 독립 검토 완료 상태로 맞췄습니다. 다음 strict build는 exit 0으로
0.54초에 완료됐고 Kotlin native 실행·설계·구조·Task·검증 페이지가 모두 nav에 등록됐습니다.

```sh
uv tool run --from uv==0.12.10 uv run --project docs --locked mkdocs build --strict
```

## 구현 확인

- production main은 `.kt`와 resources만 있고 `.java`는 0개입니다.
- Bean은 primary constructor `private val` DI이며 고정 response/storage shape는 typed class입니다.
- contract/DTO는 `data class`, entity는 ordinary class입니다. `plugin.jpa`가 만든 zero-arg constructor와
  `allOpen` 결과를 reflection 및 실제 Hibernate load로 확인했습니다. JVM reflection의 `isSynthetic` modifier 값에는 의존하지 않습니다.
- 일반 production 경계에 `!!`, coroutine, WebFlux, Java `Optional`, Base/Facade/base repository가 없습니다.
- claim INSERT/flush의 H2 23505와 SQL만 좁게 번역하고 rollback 뒤 `ReservationAttempts`가 새 proxy read를 수행합니다.
- transaction metrics는 manager listener의 실제 완료 callback을 사용합니다. commit/rollback/begin/rollback-boundary 실패를
  실제 DB 최종 상태와 함께 검사해 `committed/rolled_back/failed` tag가 맞음을 확인했고 구조화 로그는 민감 원문을 정제합니다.

## 남은 범위와 위험

- container/Compose와 예약 포트 18094, PostgreSQL, coroutine/WebFlux, auth, key 만료, 운영 부하·성능은 미구현·미검증입니다.
- H2 시험은 PostgreSQL/SQLite의 잠금·driver 보장이 아니며 실제 디스크·전원 장애를 재현하지 않습니다.
