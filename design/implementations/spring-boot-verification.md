# Spring Boot 검증 기록

Status: 실제 구현·검증 및 제품 seed 책임 분리 결과 · 2026-09-15

실행 가이드는 [README](../../java/spring-boot/README.md), 선택·transaction 의미는
[구현 설계](spring-boot.md)가 소유합니다. FastAPI 시험 통과를 Java의 검증 증거로 사용하지 않습니다.

## 환경과 명령

Task 9 (`6025aaf`)에서 Spring Data JPA **4.1.1**, Hibernate **7.4.5.Final**, Jakarta Persistence **3.2.0**으로
전환했습니다. 나머지 아래 버전은 유지했습니다. Boot 관리 버전을 사용하며 별도 Hibernate override는 없습니다.
이전 JDBC 구현의 실행·통합 기록은 아래에 보존하고 현재 JPA 결과는 다음 절에서 구분합니다.

| 항목 | 확인값 |
| --- | --- |
| Initializr·Boot | 4.1.1 |
| Gradle Wrapper | 9.7.1 |
| Java major | .java-version의 25 |
| native JDK | Temurin 25.0.4.1+1 LTS, macOS arm64, 프로젝트 시험용 /tmp 설치 |
| Docker JDK/JRE | Temurin 25, 실제 resolve 25.0.4+7 noble arm64 |
| Spring Framework | 7.0.9 |
| H2 | 2.4.240 |
| Flyway engine / 파일 생성 CLI | 12.4.0 / 13.4.0 |
| Springdoc | 3.1.1 |

Initializr metadata의 최신 stable·지원 Java/의존성 목록과 공식 호환 표를 먼저 확인했습니다.
최초 생성·시험은 설치된 Java 21을 썼고 중앙 요청에 따라 Java 25 LTS로 전환했습니다.
전역 설치·공유 DB·계정·기존 서비스 포트는 변경하지 않았습니다.

```sh
cd java/spring-boot
./gradlew clean test bootJar --no-daemon --console=plain
```

Java compiler `-Xlint:all,-processing,-serial`·`-Werror`와 strict dependency locking을 포함합니다.
이전 JDBC 구현 commit `a65cb26` 기준 clean 빌드는 **27개 시험·10 suites·실패 0·오류 0**으로 통과했습니다.
그 단계의 마지막 코드 수정 `53db988`은 아래 명령으로 영향받는 **HTTP·transaction 14개 시험·실패 0**과 bootJar를 확인했습니다.

```sh
./gradlew test --tests '*TransactionFailureTest' --tests '*HttpDatabaseTest' bootJar --no-daemon --console=plain
```

실제 pool 포화는 503이고 setAutoCommit 단계의 비일시 연결 실패는 500·INTERNAL_ERROR이며 Retry-After가 없음을 검사했습니다.
마지막 수정 후 전체 프로세스 시험을 다시 실행한 것으로 표시하지 않습니다.
테스트 결과는 `build/reports/tests/test/index.html`, JUnit XML은 `build/test-results/test/`입니다.
lockfile 생성은 공식 `./gradlew test bootJar --write-locks`로 수행했습니다.
migration 파일은 공식 `flyway help add` 확인 후 `flyway add -add.version=1|2 -add.timestamp=never ...`로 만들었습니다.

## Task 10 코드 정리 검증

2026-09-08, `1b3cc63` 기반 공유 checkout에서 Spring Boot 소유 경로만 수정했습니다.
지정된 `/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home/bin/java`의 존재와 Java 25.0.4.1을 확인하고
Gradle `--help`를 확인한 뒤 명령별 JAVA_HOME·PATH로 실행했습니다. 머신 기본값·라이브러리·ORM·migration·Compose는 변경하지 않았습니다.

```sh
cd java/spring-boot
JAVA_HOME=/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home \
PATH=/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home/bin:$PATH \
./gradlew clean test bootJar --no-daemon --console=plain
```

최종 코드 기준 **35개 시험·11 suites·실패 0·오류 0·skip 0**, 41초에 통과했습니다.
기존 34개 시험은 유지하고 실제 HTTP의 공개 오류 위치·코드 회귀 시험 하나를 추가했습니다.
누락은 `body/product_id`·REQUIRED, null·숫자·boolean·배열·객체는 같은 위치·INVALID,
unknown field·잘못된 JSON은 빈 위치·INVALID임을 확인합니다. type/title/status와 request ID의 body/header 일치도 검사합니다.
예약 전용 DatabindException 분기 없이 기존 deserializer의 InvalidInput만으로 이 계약이 유지됩니다.
기존 전체 시험이 no-db·proxy·rollback/commit 실패·claim 경합·JPQL flush/clear·FK 순서·nanosecond replay·실제 완료 metrics를 검증했습니다.
`git diff --check`도 통과했습니다. 로그는 `/tmp/spring-task10-build.log`, HTML/JUnit XML은 기존 build 경로입니다.

임시 DB·OS 임시 포트를 쓰는 기존 시험만 실행했으며 실행 중인 로컬 서비스·공유 DB는 건드리지 않았습니다.
중앙에서 코드 차이와 JUnit XML의 결과를 확인했습니다. 이번 변경의 Docker 배포·공유 수집 검증은 수행하지 않았으며
H2 claim table의 단일 PK·Hibernate INSERT SQL에 의존하는 기존 분류 제한도 유지합니다.

## Task 11 reservation 명명 검증

`saveReservationAndReplay`와 `findMatchingReplay`로 repository와 실제 Service callsite만 변경했습니다.
별도 repository·테스트를 추가하지 않았으며 기존 strict clean test와 bootJar로 paired persist·flush,
replay mismatch, proxy commit/rollback과 `ReservationAttempts`의 rollback 뒤 fresh read를 재검증했습니다.
격리 Temurin 25.0.4.1에서 `./gradlew clean test bootJar --no-daemon --console=plain`은
35개·11 suites·실패/오류/skip 0으로 통과했습니다. 기본 환경의 Java 25 미탐지는 코드 실패와 구분합니다.

## Task 12 제품 seed 책임 분리 검증

새 `ProductSeedService`의 실제 Spring proxy, 음수 거절, 신규 stock 반환과 반복 실행의 기존 stock 보존을
`HttpDatabaseTest`에서 확인했습니다. `JpaPersistenceTest`는 concrete `ProductSeedRepository`를 주입해
pending insert 뒤 bulk update의 flush·detach 의미를 계속 검증합니다. `LifecycleTest`는 no-db에서
새 Service와 Repository가 등록되지 않음을 확인합니다. 세 focused suite 18개와
격리 Temurin 25.0.4.1의 strict clean test/bootJar 전체 35개·11 suites를 실패 없이 통과했습니다.

`SeedConfiguration`은 새 Service를 호출하며 예약 Service/Repository에는 seed 호출이 남지 않습니다.
find-then-persist 의미만 유지하며 동시 seed upsert를 주장하거나 새 migration을 추가하지 않았습니다.
예약 commit/rollback·fresh replay read와 기존 transaction metrics는 전체 시험으로 재검증했습니다.

## Task 9 JPA 검증

2026-09-08, 기존 `origin/main`을 정상 fast-forward merge한 뒤 승인 설계 `4301427`을 먼저 기록했습니다.
프로젝트 시험용 JDK는 `/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home`을 사용했고 머신 기본값은 변경하지 않았습니다.
Gradle `--help`와 공식 locking 문서를 확인했습니다. Gradle에는 dependency add 명령이 없으므로
DSL의 starter를 변경한 뒤 공식 dependency resolution 명령으로 lockfile을 생성했습니다.

```sh
cd java/spring-boot
JAVA_HOME=/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home ./gradlew --help
JAVA_HOME=/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home ./gradlew dependencies --write-locks --no-daemon --console=plain
JAVA_HOME=/tmp/spring-jdk25/jdk-25.0.4.1+1/Contents/Home ./gradlew clean test bootJar --no-daemon --console=plain
```

최종 명령은 strict lock·compiler 경고 오류화 상태로 **34개 시험·11 suites·실패 0·오류 0·skip 0**,
35초에 통과했습니다. 전체 HTTP·독립 JVM·종료 시험을 포함하며 기존 실패 검증을 제거하거나 완화하지 않았습니다.
JUnit XML·HTML 위치는 기존과 같고 실행 로그는 `/tmp/spring-jpa-final.log`입니다.
앞선 실행은 pool timeout 예외 포장과 ProcessWorker의 JDBC manager 가정 때문에 실패했고 수정 후 전체 재검증했습니다.
새 시험의 schema 오류 메시지·rollback 예외 기대값도 실제 Hibernate 7.4.5/Spring 7 동작으로 정정했습니다.

| 실제 시험 | JPA 전환 증거 |
| --- | --- |
| JpaPersistenceTest | manager Bean 정확히 1개·JpaTransactionManager, pending seed flush, bulk UPDATE 후 기존 entity detach·재조회 stock 1·독립 연결 commit 상태 |
| JpaPersistenceTest | 두 public proxy transaction이 barrier 뒤 동일 claim을 persist·flush, 승자 1·IdempotencyClaimed 1·committed 1·rolled_back 1·DB claim 1 |
| JpaPersistenceTest | batch_size=16·order_inserts=true에서도 claim 충돌 분류와 FK 순서 성공, 결과 CHECK 실패 때 stock·claim·예약·결과 모두 이전 상태 |
| TransactionFailureTest | 실제 Connection.commit gate 중 HTTP 미완료·committed 미증가, 실패500·전체 rollback·failed 1·동일키 재시도 성공 |
| TransactionFailureTest | CHECK 및 예약 product UNIQUE의 flush 실패는500, claim 충돌로 재생하지 않음·전체 rollback·성공 counter 없음 |
| TransactionFailureTest | 실제 rollback 실행 뒤 SQLException 주입 시 JpaSystemException·failed 1·rolled_back/committed 0·독립 연결 상태 보존 |
| HttpDatabaseTest | 실제 pool 포화503·H2 lock timeout503·키/상품별 경합·정확한 replay와 HTTP 계약 유지 |
| LifecycleTest | no-db에는 DataSource·EntityManagerFactory·transaction manager·ProductRepository 없음, 예약404·readiness200 |
| LifecycleTest | available을 VARCHAR로 변경하면 SchemaManagementException으로 시작 실패, Hibernate가 schema를 복구하지 않음 |
| MigrationTest | V1 데이터를 V2로 올린 뒤 JPA 시작·9자리 소수 timestamp의 정확한 HTTP body201 재생 |
| ProcessRecoveryTest | JpaTransactionManager callback으로 기존 독립 JVM same/different-key·commit 전후 kill·embedded 재시작 4개 시험 유지 |

`ddl-auto=validate`는 Hibernate가 호환으로 판단하는 타입을 허용합니다. INTEGER→BIGINT widening은 통과했으며,
모든 schema 차이를 탐지한다고 주장하지 않습니다. CHECK·FK·unique·migration history는 Flyway와 실제 DB 시험으로 검증합니다.
V1/V2 파일·기존 문자열 UTC column은 변경하지 않았으며 추가 migration도 없습니다.
claim 분류는 현재 H2 claim table의 단일 PK와 Hibernate INSERT SQL에 의존합니다.
다른 unique 제약을 해당 table에 추가하거나 DB/provider를 바꿀 때는 분류 시험을 갱신해야 합니다.

rollback 장애 주입은 실제 rollback 후 acknowledgement 오류를 모사합니다. DB가 rollback 자체를 거부하거나
commit 결과가 불명인 물리 장애에서 데이터 원자성·자동 복구를 증명하지 않습니다.
JPA 전환 후 실제 이미지·기존 H2 volume·Prometheus의 중앙 확인은 다음 절에 있습니다.
이전 JDBC 이미지의 검증과 구분합니다.

## JPA 로컬 통합 검증

2026-09-08 main에서 코드 `6025aaf`를 검토·통합한 뒤 공통 Compose로 새 이미지를 빌드했습니다.
`./scripts/compose.sh spring-boot build api`의 strict locked bootJar가 통과했으며,
실행 이미지 ID는 `sha256:d28ef99593d07802a63f2ed20732bc35299b8436d9a022d65f844a057bcb15cf`입니다.
UID 10001·내부 8080·게시 18086·기존 데이터 volume을 유지했습니다.

| 확인 | 실제 결과 |
| --- | --- |
| DB 비활성 이미지 | readiness·metrics·OpenAPI 200, 예약 POST 404·OpenAPI 제외, DB transaction·Hikari 지표 없음 |
| 기존 데이터 업그레이드 | 서버 정지 후 H2 파일 백업, 기존 상품 1개·예약/멱등 결과/claim 각 3개가 JPA 실행 후에도 모든 필드 동일 |
| 기존 HTTP 응답 | JDBC 버전의 원래 body·201·Idempotency-Replayed true가 JPA 전환 및 재시작 후 동일 |
| 동일 키 동시 요청 | 재고 2에서 요청 6개 모두 동일 body 201, 최초 처리 1개·재생 5개 |
| 서로 다른 키 동시 요청 | 남은 재고 1에서 요청 6개 중 성공 1개·SOLD_OUT 409 5개 |
| 영속 상태 | 새 상품 재고 0, 새 예약·멱등 결과 각 2개, 전체 claim 5개; 기존 데이터 행 비교 일치 |
| 오류 계약 | 다른 입력의 동일 키 409, 미존재 상품 404, 입력 오류 3종 422, GET 예약 405·Allow POST·Problem·request ID |
| 재시작 | 기존·새 예약 모두 원래 body 재생, healthy, OOMKilled false |
| 관측 | 새 프로세스의 실제 두 replay 후 committed 2·duration count 2, Hikari active 0·max 4, HTTP·JVM 지표 존재 |
| Prometheus | 재시작 이후 scrape에서 spring-boot UP·committed 2·pool max 4; FastAPI·NestJS도 UP 유지 |

읽기 전용 H2 Shell로 전환 전후 파일 사본을 조회해 기존 행을 비교했습니다.
공식 `org.h2.tools.Shell -help`를 확인한 뒤 `ACCESS_MODE_DATA=r`을 사용했습니다.
원본 백업은 `/tmp/backend-spring-jpa-backup.bA96Iq/data`, 전환 후 사본은
`/tmp/backend-spring-jpa-after.dQejmC/data`에 보관합니다.
HTTP 증거는 `/tmp/backend-spring-jpa-smoke-result.json`, 새 프로세스 scrape는
`/tmp/backend-spring-jpa-metrics.prom`입니다. 임시 증거는 배포 입력이 아닙니다.
소규모 요청 후 메모리 단일 측정은 258.8 MiB / 512 MiB이며 운영 부하·용량 보장이 아닙니다.
MkDocs strict build와 로컬 가이드의 PC 화면에서 JPA Mermaid 흐름을 확인했습니다.

## 실행한 시험

| 시험 | 확인 내용 |
| --- | --- |
| GreetingServiceTest | context 없는 생성자 DI·고정 Clock |
| TemplateApplicationTests | no-db context |
| HttpDatabaseTest | 실제 소켓·file DB, 인사/data·Problem·request ID·404/405 Allow·엄격 입력422·health/metrics/docs |
| HttpDatabaseTest | 최초201·원래body/status 재생·다른입력409·품절·미존재·다중HTTP 동일/다른키·잠금/pool timeout·독립상품진행 |
| HttpDatabaseTest | 클라이언트가 응답을 버린 뒤 재시도·재고/예약/결과 독립 연결 확인 |
| TransactionFailureTest | public proxy checked/unchecked rollback·중간 constraint 실패·JDBC commit 실패·claim 전체 rollback |
| TransactionFailureTest | commit gate 중 응답 미완료·committed 지표 미증가·500 번역·같은키 재시도 |
| ProcessRecoveryTest | 독립 JVM 같은키·다른키 경합, commit 전/후 kill, commit 후 응답 미전달 상태 재생 |
| ProcessRecoveryTest | embedded file DB의 실제 JVM 종료·재시작 원래 결과 재생 |
| MigrationTest | V1→V2 데이터 보존·claim backfill·guard 제거·반복 실행·실패 migration |
| LifecycleTest | 빈 URL 자동 비활성·healthy readiness·예약 제외·잘못된 설정·부분 시작 실패 pool 종료 |
| ShutdownTest | 실제 SIGTERM 중 진행 HTTP 요청 완료·프로세스 종료·file DB 잠금 반환 |
| ObservationTest | 서버ID·MDC 정리·원래 chain 예외 보존·로그 failure/type·metrics 실패 격리 |
| SpecialHttpTest | 204·파일·실제 committed stream·429 Retry-After·error dispatch·요약 중복 없음·민감 원문 제외 |

테스트는 업무 transaction을 자동 rollback하는 테스트 transaction으로 감싸지 않습니다.
독립 JDBC 연결에서 commit 이후 저장 상태를 확인합니다.
TCP 시험은 중앙 승인 아래 127.0.0.1·OS 임시포트·임시파일을 쓰며 자기 프로세스만 종료합니다.
embedded 파일의 다중 JVM 접근 제한을 TCP 시험과 구분합니다.

Task 1–8의 commit 실패는 JdbcTransactionManager, Task 9는 JpaTransactionManager의 실제 Connection.commit 호출 지점에 SQLException을 주입합니다.
H2가 deferred FK를 지원한다고 가정하지 않으며 물리 디스크 고장을 일으키지 않습니다.
관측 counter는 실패 1·committed 0과 영속 상태를 대조한 뒤 재시도 성공을 확인합니다.

Spring 7.0.9에서는 OutputStream.flush가 기본적으로 network flush가 아니므로 stream 시험은
HttpServletResponse.flushBuffer로 실제 committed 상태를 만든 뒤 IOException을 발생시킵니다.
이미 전송된 body에 Problem 응답을 덧붙이지 않는 것과 정상 전송 성공은 구분합니다.

## 이전 JDBC 구현의 native·이미지·재사용

native 게시 127.0.0.1:18085를 실행 직전 점유 확인 후 사용했습니다.
임시 작업 디렉터리의 file DB에 seed→예약201→SIGTERM→새 JVM→동일body201 replay를 확인했습니다.
native stdout 로그의 JSON·서버ID·민감 클라이언트ID 제외를 검사했습니다.
실행 로그는 `/var/folders/lt/6xldspxd1kd2wnx9hmc8qjv80000gn/T/spring-native-final-0euqy6vl/`,
비밀 없는 scrape는 `/tmp/spring-final-metrics.prom`에 남겼습니다. 두 경로는 로컬 임시 증거이며 배포 입력이 아닙니다.

```sh
docker build --build-arg JAVA_VERSION="$(cat java/spring-boot/.java-version)" \
  -t backend-template-spring:local java/spring-boot
```

Docker locked 빌드는 통과했습니다. JAVA_VERSION 기본값을 두지 않으므로 Docker 정적 lint의
InvalidDefaultArgInFrom 경고 2개가 있으며 실제 명령은 필수 arg를 전달합니다.
이미지는 curl healthcheck·UID10001·/app/data·내부8080을 사용합니다.
Compose의 127.0.0.1:18086 실행·수집기 확인 결과는 아래 통합 검증에 기록합니다.

`a65cb26` 구현 이미지 manifest는 `sha256:898234f975f4901933b91c4d2c9c47cba6176d91eacb3b21def9557cfeee779b`입니다.
이후 `53db988`의 오류 번역 수정까지 포함한 Compose 이미지를 다시 빌드·실행했습니다.
`git archive a65cb26 java/spring-boot`를 `/tmp/spring-template-copy-a65cb26/`에 풀어
새 위치에서 `./gradlew bootJar --no-daemon --console=plain`을 실행해 통과했습니다.
복사한 start.sh를 독립 임시 포트 57097에서 실행해 DB 비활성 readiness 200·인사 응답·예약 404를 확인했습니다.

분리 작업 중 발생한 README 발행 링크 경고는 main의 문서 hook·메뉴 통합으로 해결했고 MkDocs strict build가 통과했습니다.

## 이전 JDBC 구현의 로컬 통합 검증

2026-09-08 main에서 `.java-version`을 읽는 공통 Compose build와 UID 10001 실행을 확인했습니다.
DB 비활성 시 health 200·예약 404·OpenAPI 제외, H2 활성 시 migration·seed·예약 201이 통과했습니다.
입력 오류 3종은 422·Problem·request ID, GET 예약은 405·Allow를 반환했습니다.
동일 body 재생·다른 입력의 동일 키 409·없는 상품 404가 통과했습니다.
재고 3에서 최초 예약 후 6개 병렬 요청은 성공 2개·품절 4개였고, 최종 이미지로 교체한 뒤에도 원래 body를 재생했습니다.
Prometheus job=spring-boot UP과 Micrometer HTTP/JVM/Hikari·업무 transaction 지표를 확인했습니다.
Grafana의 Spring Boot 대시보드를 PC 화면에서 확인했습니다.
소규모 요청 후 컨테이너 메모리 단일 측정은 203.5 MiB / 한도 512 MiB이며 운영 용량 보장이 아닙니다.

## 구현 commit

| commit | 내용 |
| --- | --- |
| 27305d3 | Initializr 생성·Java 21 최초 기반 |
| 2d745e0 | Java 25·HTTP·H2 최초 예약과 실제 HTTP 시험 |
| a65cb26 | 키별 claim·자동 no-db·중앙 리뷰·실패/복구/수명/관측 시험·실행 안내 |
| 73af314 | clean 27개·복사 빌드/실행·중앙 MkDocs hook 미통합 기록 |
| 53db988 | 실제 pool timeout과 비일시 transaction 시작 실패의 HTTP 번역 분리 |

후속 문서 commit은 위 구현 결과와 중앙 통합 확인을 기록하며 코드 revision과 구분합니다.

## 실제 metrics 대응

| 이름·label | 의미 |
| --- | --- |
| http_server_requests_seconds_count/sum/bucket | Micrometer HTTP, method/status/uri template/outcome/exception/error |
| jvm_memory_used_bytes | area·id별 JVM 메모리 |
| hikaricp_connections_active/idle/pending/max | pool별 실제 연결 |
| hikaricp_connections_timeout_total | pool 획득 timeout |
| jdbc_connections_active/idle/max/min | DataSource 관측 |
| db_transactions_total | role=primary, outcome=committed/rolled_back/failed |
| db_transaction_duration_seconds_count/sum/max | 실제 transaction 완료 시점까지 |

native 재시작 후 scrape에서 `db_transactions_total{outcome="committed",role="primary"} 1.0`과
`http_server_requests_seconds_count{error="none",exception="none",method="POST",outcome="SUCCESS",status="201",uri="/v1/reservations"} 1`을 확인했습니다.
재시작은 process counter를 초기화합니다. 재생 transaction도 committed 한 건이며 신규 예약 수가 아닙니다.
request ID·멱등 key·raw query를 labels에 넣지 않습니다.
http.completed는 Servlet 처리 완료이고 실제 상대 수신·무손실 전달을 뜻하지 않습니다.

## 미검증·제한

- PostgreSQL·SQLite·H2 PostgreSQL compatibility mode는 검증하지 않았습니다.
- 실제 디스크 오류·전원 차단·운영 부하·성능/용량 수치·클러스터·Replica·sharding은 범위 밖입니다.
- JDBC commit 결과가 불명인 외부 저장 장애를 임의로 재시도하지 않습니다. 같은 키 조회·재생으로 확인합니다.
- H2 DDL의 transactional rollback을 PostgreSQL과 동일하게 주장하지 않습니다. 실패 migration은 시작을 차단합니다.
- 키 만료·정리·인증 scope·분산 작업·운영 로그 수집/보존·알림은 구현하지 않았습니다.
- Docker 플랫폼은 arm64에서 검증하며 다른 CPU/OS 결과로 확대하지 않습니다.
