# Kotlin Spring Boot Backend Template

Kotlin 2.3.21 · Java 25 · Spring Boot 4.1.1 · Spring MVC · JPA/Hibernate · H2 · Flyway.
이 앱은 `java/spring-boot/`와 독립적으로 실행되며 native 기본 주소는
http://127.0.0.1:18093 입니다.

문서 지도: [구현 색인](../../design/implementations/README.md) ·
[설계](../../design/implementations/kotlin-spring-boot.md) · [구조](../../design/implementations/kotlin-spring-boot-structure.md) ·
[Task](../../design/implementations/kotlin-spring-boot-tasks.md) · [검증](../../design/implementations/kotlin-spring-boot-verification.md) ·
[루트 README](../../README.md) · [적용 Runbook](../../RUNBOOK.md)

## 빌드와 DB 없는 실행

`.java-version`은 요구 major를 기록할 뿐 JDK를 설치하거나 현재 shell을 전환하지 않습니다.
JDK 25의 실제 경로를 사용해 `java`, Gradle launcher/toolchain이 모두 25인지 확인합니다.

```sh
cd kotlin/spring-boot
export JAVA_HOME='/path/to/jdk-25'
export PATH="$JAVA_HOME/bin:$PATH"
java --version
./gradlew --version
./gradlew clean test bootJar --no-daemon --console=plain
./scripts/start.sh
```

기본 `DB_PRIMARY_URL`은 비어 있습니다. 이때 DB·Flyway·JPA·예약 route는 구성하지 않고
greetings, health, docs, metrics는 동작합니다.

```sh
curl 'http://127.0.0.1:18093/v1/greetings?name=Marin'
curl http://127.0.0.1:18093/health/ready
```

## 독립 H2 file과 예약

앱을 종료한 뒤 같은 shell에서 Kotlin 앱 전용 DB URL을 설정합니다.

```sh
export DB_PRIMARY_URL='jdbc:h2:file:./data/template;DB_CLOSE_ON_EXIT=FALSE;LOCK_TIMEOUT=1000;WRITE_DELAY=0'
./scripts/start.sh --seed --app.seed.product-id=demo --app.seed.stock=10
./scripts/start.sh
```

```sh
curl -i http://127.0.0.1:18093/v1/reservations \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example-1' \
  -d '{"product_id":"demo"}'
```

첫 요청은 201과 `Idempotency-Replayed: false`, 같은 입력의 재요청은 저장된 body와
`Idempotency-Replayed: true`를 반환합니다. 다른 입력에 같은 key는 409, 품절은 409,
제품 없음은 404입니다. embedded H2 file은 한 JVM만 열 수 있으므로 seed 전 서버를 종료합니다.

| 경로 | 응답 |
| --- | --- |
| `/`, `/v1/greetings` | typed `data` 성공 응답 |
| `POST /v1/reservations` | DB 활성 시 예약 생성·재생 |
| `/health/live`, `/health/ready` | 공통 health body |
| `/metrics` | Prometheus metrics |
| `/docs`, `/openapi.json` | Swagger UI·OpenAPI |

공개 오류는 `application/problem+json`이며 server-owned `X-Request-ID`를 body와 맞춥니다.
로그는 ECS JSON stdout이고 raw query/body/key와 예외 원문을 기록하지 않습니다.

## 환경과 시험

`.env.example`은 값 목록일 뿐 자동으로 읽히지 않습니다. native 실행에서는 shell 환경으로 전달합니다.
container와 Compose는 아직 구현하지 않았고 18094만 후속 게시 포트로 예약했습니다.

`./gradlew test`는 Java 구현의 35개 실제 계약 scenario를 이식한 Java integration test와
Kotlin proxy/JPA/null/Jackson 경계 test를 실행합니다. 임시 file DB와 OS 임시 포트를 사용하며
실제 운영 DB·PostgreSQL·외부 인프라를 변경하지 않습니다.

의존성 변경 뒤 `./gradlew dependencies --write-locks`로 lockfile을 다시 생성·검토합니다.
일반 빌드는 strict lock과 Kotlin warnings-as-errors로 실행됩니다.
