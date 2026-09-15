# Kotlin Spring Boot 검증 기록

Status: **Task 1–8 구현·자동 시험·native 재시작 검증 완료 · Task 9 독립 검토 대기** · 2026-09-16

대상 revision은 작업 중인 `kotlin/spring-boot/`와 Kotlin 설계 문서이며 아직 commit 전입니다.
공통 계약의 근거는 [Java 검증 기록](spring-boot-verification.md), Kotlin 고유 선택은
[구현 설계](kotlin-spring-boot.md)를 봅니다. Compose·container·공용 문서 통합은 실행하지 않았습니다.

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

결과: 54초, 9 tasks 실행, `BUILD SUCCESSFUL`. `compileJava`는 `NO-SOURCE`였고 Kotlin compiler warning은 0개였습니다.
생성된 `gradle.lockfile`로 strict resolution이 적용됐습니다.

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
빌드한 JAR를 loopback 18093에서 DB URL 없이 실행해 다음을 확인했습니다.

- `/health/ready` 200, `{"status":"ready"}`
- `/v1/greetings?name=Marin` 200과 typed `data` body
- `POST /v1/reservations` 404
- 종료 뒤 18093 listener 없음

독립 임시 경로 `/tmp/kotlin-native-ab1e.Y5icUI/template`에 stock 2를 seed한 뒤 서버를 실행했습니다.
key `native-replay`의 첫 요청은 201, `Idempotency-Replayed: false`와 아래 저장 결과를 반환했습니다.

```json
{"data":{"reservation_id":"b561197a4ac74b0ca7d68afb1f6df9aa","product_id":"demo","created_at":"2026-09-15T17:28:58.614856Z"}}
```

SIGINT로 소유 process를 종료하고 같은 file로 새 JVM을 시작한 뒤 동일 요청을 보냈습니다.
두 번째 응답은 201, `Idempotency-Replayed: true`였고 body byte가 첫 응답과 같았습니다.
마지막 JVM도 종료했으며 기존 18090·18092 서비스에는 접근하지 않았습니다.

## 구현 확인

- production main은 `.kt`와 resources만 있고 `.java`는 0개입니다.
- Bean은 primary constructor `private val` DI이며 고정 response/storage shape는 typed class입니다.
- contract/DTO는 `data class`, entity는 ordinary class입니다. `plugin.jpa`가 만든 zero-arg constructor와
  `allOpen` 결과를 reflection 및 실제 Hibernate load로 확인했습니다. JVM reflection의 `isSynthetic` modifier 값에는 의존하지 않습니다.
- 일반 production 경계에 `!!`, coroutine, WebFlux, Java `Optional`, Base/Facade/base repository가 없습니다.
- claim INSERT/flush의 H2 23505와 SQL만 좁게 번역하고 rollback 뒤 `ReservationAttempts`가 새 proxy read를 수행합니다.
- transaction metrics는 manager listener의 실제 완료 callback을 사용하고 구조화 로그는 민감 원문을 정제합니다.

## 남은 범위와 위험

- Task 9 독립 review·수정·최종 재검증은 coordinator가 별도로 dispatch합니다.
- Task 10 루트 README·구현 index·MkDocs nav 통합은 아직 하지 않아 현재 strict docs build에는 새 페이지 미등록 warning이 납니다.
- container/Compose와 예약 포트 18094, PostgreSQL, coroutine/WebFlux, auth, key 만료, 운영 부하·성능은 미구현·미검증입니다.
- H2 시험은 PostgreSQL/SQLite의 잠금·driver 보장이 아니며 실제 디스크·전원 장애를 재현하지 않습니다.
