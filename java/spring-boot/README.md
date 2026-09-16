# Spring Boot Backend Template

Java 25 · Spring Boot 4.1.1 · Spring Data JPA 4.1.1 · Hibernate 7.4.5.Final · H2 2.4.240.
Java major의 정본은 `.java-version`, 의존성의 정본은 Gradle 설정과 생성된 lockfile입니다.
예약 코드·transaction·JPA의 내부 동작은 [로직과 내부 동작](../../design/implementations/spring-boot-internals.md),
설계·시험 상세는 [Spring Boot 설계](../../design/implementations/spring-boot.md)를 봅니다.

문서 지도: [구현 색인](../../design/implementations/README.md) ·
[설계](../../design/implementations/spring-boot.md) · [구조](../../design/implementations/spring-boot-structure.md) ·
[Task](../../design/implementations/spring-boot-tasks.md) · [검증](../../design/implementations/spring-boot-verification.md) ·
[루트 README](../../README.md) · [적용 Runbook](../../RUNBOOK.md)

## 빌드와 DB 없는 실행

JDK 25를 먼저 설치합니다. 아래 `/path/to/jdk-25`를 설치 경로로 바꾸고 현재 셸에서만 지정합니다.
`java`·`javac`가 모두 25인지, Gradle의 Launcher JVM·Daemon JVM도 의도한 JDK인지 확인합니다.
`.java-version` 파일만으로 셸의 Java가 전환되지는 않습니다.

```sh
cd java/spring-boot
export JAVA_HOME='/path/to/jdk-25'
export PATH="$JAVA_HOME/bin:$PATH"
java --version
javac --version
./gradlew --version
./gradlew clean test bootJar --no-daemon --console=plain
./scripts/start.sh
```

기본 주소는 http://127.0.0.1:18085 입니다.
`DB_PRIMARY_URL`이 비어 있으면 DB·migration·예약 경로를 구성하지 않습니다.
인사·health·metrics·API 문서는 DB 없이도 동작합니다.

```sh
curl 'http://127.0.0.1:18085/v1/greetings?name=Marin'
curl http://127.0.0.1:18085/health/ready
```

인사는 `{"data":{"message":"Hello, Marin!","generated_at":"..."}}`,
readiness는 `{"status":"ready"}`입니다. 종료는 Ctrl+C입니다.

## H2 file DB와 예약

서버가 종료된 상태에서 같은 셸에 DB URL을 지정합니다.
아래 URL은 현재 구현 디렉터리의 `data/`에 영속 파일을 만듭니다.

```sh
export DB_PRIMARY_URL='jdbc:h2:file:./data/template;DB_CLOSE_ON_EXIT=FALSE;LOCK_TIMEOUT=1000;WRITE_DELAY=0'
java -jar build/libs/backend-template-0.0.1-SNAPSHOT.jar --seed --app.seed.product-id=demo --app.seed.stock=10
./scripts/start.sh
```

Flyway가 시작 시 migration을 적용하고 실패하면 요청을 받지 않습니다.
JPA는 schema를 검증하며 생성·수정하지 않습니다. 기존 V1/V2 H2 파일은 그대로 사용합니다.
seed는 제품이 없을 때만 수량을 넣으며 기존 재고를 덮어쓰지 않습니다.
embedded H2 파일은 한 JVM만 열 수 있으므로 **서버를 종료한 뒤 seed**합니다.
H2 console은 제공하지 않습니다.

```sh
curl -i http://127.0.0.1:18085/v1/reservations \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: example-1' \
  -d '{"product_id":"demo"}'
```

처음은 201·`Idempotency-Replayed: false`, 같은 키·같은 입력의 재시도는 원래 body와 201을
`Idempotency-Replayed: true`로 반환합니다. 재시작 후에도 재생합니다.
같은 키·다른 입력은 409 `IDEMPOTENCY_CONFLICT`, 품절은 409 `SOLD_OUT`,
제품 없음은 404 `PRODUCT_NOT_FOUND`입니다. 실패한 요청은 키를 소비하지 않습니다.
키 범위는 이 DB의 예약 생성 전체이며 인증된 사용자별 범위나 만료는 구현하지 않습니다.

## 입력과 관측

| 주소 | 의미 |
| --- | --- |
| `/`, `/v1/greetings?name=Marin` | data 성공 envelope |
| `POST /v1/reservations` | DB 활성 때만 예약 |
| `/health/live`, `/health/ready` | 공통 health body, readiness는 필수 DB 연결 포함 |
| `/actuator-health` | Actuator 상세 형식, 공통 envelope 제외 |
| `/metrics` | Micrometer Prometheus exporter |
| `/docs`, `/openapi.json` | Swagger UI·OpenAPI |

잘못된 JSON·타입·누락·알 수 없는 body 필드는 422입니다.
공개 오류는 `application/problem+json`이며 서버가 생성한 32자리 request ID를
`X-Request-ID`와 `request_id`에 넣습니다. 클라이언트 request ID는 신뢰하지 않습니다.
예약 입력은 product_id 하나이고 수량은 항상 1입니다.

로그는 Boot ECS JSON stdout이며 원시 경로·query·body·key·예외 메시지를 기록하지 않습니다.
검토하지 않은 framework 메시지는 `framework.event`로 정제하고 logger·오류 타입을 남깁니다.
`http.completed`는 Servlet 동기 처리 또는 async 완료를 뜻하며 상대 클라이언트의 수신 확인이 아닙니다.
DB transaction 지표는 실제 완료 callback에서 기록하며 재생·seed transaction도 포함하므로 신규 예약 수가 아닙니다.
지표 label에 키·request ID·원시 URL을 넣지 않습니다.

## 환경과 컨테이너

Gradle toolchain과 중앙 Compose의 Docker build arg는 `.java-version`을 읽습니다.
이 파일은 Java major만 지정하며 JDK를 설치하지 않습니다. 로컬 JDK는 직접 준비하고
`gradlew`의 `JAVA_HOME`과 start script가 사용하는 `PATH`의 Java를 맞춥니다.
Docker는 Temurin JDK로 빌드하고 JRE로 실행하며, major 태그는 patch까지 고정하지 않습니다.
`bootJar` 단독 실행에는 테스트가 포함되지 않으므로 검증할 때는 앞의 `clean test bootJar` 명령을 사용합니다.

`.env.example`은 Compose용 입력 예시입니다.
Boot와 start script는 이 파일을 자동으로 읽지 않습니다. native 실행에서는 셸 환경으로 전달합니다.
앱별 설정은 `APP_NAME`, `SERVICE_VERSION`, `APP_ENVIRONMENT`, `LOG_LEVEL`,
`SERVER_HOST`, `SERVER_PORT`, `SHUTDOWN_TIMEOUT_SECONDS`입니다.
DB 설정은 `DB_PRIMARY_URL`, `DB_USERNAME`, `DB_PASSWORD`,
`DB_POOL_SIZE`(1–32), `DB_POOL_TIMEOUT_MS`(250–30000)입니다.
잠금 대기시간은 H2 URL의 `LOCK_TIMEOUT` 밀리초 값입니다.
`SPRING_PROFILES_ACTIVE=no-db`로 명시적으로 DB를 끌 수도 있습니다.

저장소 루트에서 실행합니다. H2 파일은 한 JVM만 열 수 있으므로 seed 전에 앱을 중지합니다.

```sh
export DB_PRIMARY_URL='jdbc:h2:file:/app/data/template;DB_CLOSE_ON_EXIT=FALSE;LOCK_TIMEOUT=1000;WRITE_DELAY=0'
./scripts/compose.sh spring-boot build api
./scripts/compose.sh spring-boot stop api
./scripts/compose.sh spring-boot run --rm --no-deps api --seed --app.seed.product-id=demo --app.seed.stock=10
./scripts/compose.sh spring-boot up --no-build --wait api
```

중앙 Compose가 실행·포트·모니터링을 관리합니다. 별도 Compose는 만들지 않습니다.
컨테이너는 UID 10001, 내부 8080, 데이터 `/app/data`, 게시 `127.0.0.1:18086`입니다.
DB 활성 URL 예시는 `jdbc:h2:file:/app/data/template;DB_CLOSE_ON_EXIT=FALSE;LOCK_TIMEOUT=1000;WRITE_DELAY=0`입니다.
Docker HEALTHCHECK는 curl로 `/health/ready`를 확인합니다.
[Swagger](http://127.0.0.1:18086/docs)에서 예약을 호출하거나 위 curl의 포트를 18086으로 바꿉니다.
종료는 `./scripts/compose.sh spring-boot stop api`이며 데이터는 유지됩니다.
공유 수집기는 [로컬 모니터링](../../design/implementations/local-monitoring.md)을 따릅니다.

## 검증과 기능 추가

`./gradlew test`는 임시 file DB·OS 임시 포트를 쓰고 일부 독립 JVM 시험에만 loopback H2 TCP 서버를 만듭니다.
JUnit 결과는 `build/reports/tests/test/index.html`에서 확인합니다.
H2 시험은 PostgreSQL·SQLite 잠금 검증이 아니며 PostgreSQL compatibility mode도 사용하지 않습니다.
실제 디스크 고장·전원 차단·운영 부하·인증·외부 API·분산 transaction은 범위 밖입니다.

HTTP DTO는 `dto/`, 내부 결과는 `contracts/`, 업무는 `services/`, JPA entity·저장은 `repositories/`에 추가합니다.
Entity를 Service·Controller의 계약으로 반환하지 않습니다. `open-in-view=false`이므로 필요한 조회·변환은 저장 경계 안에서 끝냅니다.
쓰기 transaction은 public Service의 `@Transactional(rollbackFor = Exception.class)` proxy 경계에 둡니다.
Controller는 proxy가 commit한 후 응답을 만들고 Repository는 commit하지 않습니다.
예약의 unique claim 충돌 복구만 `ReservationAttempts`가 담당하며 무제한 자동 재시도는 없습니다.

새 migration은 공식 Flyway CLI의 `help add`를 확인한 뒤 `flyway add`로 생성하고 SQL 본문을 편집합니다.
기존 V1·V2를 수정하지 않고 다음 버전으로 추가합니다.
의존성 변경 시 Gradle DSL을 편집한 뒤 `./gradlew dependencies --write-locks`로 lockfile을 생성·검토하고 전체 빌드를 실행합니다.
일반 빌드는 strict lock으로 수행됩니다. Java compiler의 `-Xlint`·`-Werror`가 타입·compiler 경고를 검사합니다.
