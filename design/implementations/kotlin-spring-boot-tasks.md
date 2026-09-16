# Kotlin Spring Boot 단계별 구현 task

Status: **Task 1–10 구현·독립 검토·자동 시험·native·문서 통합 검증 완료** · 2026-09-16

대상은 `kotlin/spring-boot/` 하나입니다. 설계는 [구현 설계](kotlin-spring-boot.md), 파일 책임은
[구조](kotlin-spring-boot-structure.md), 공통 수락 계약과 기존 증거는 [Java 검증 기록](spring-boot-verification.md)을 봅니다.
Task 1–8의 명령·HTTP·DB 증거는 [Kotlin 검증 기록](kotlin-spring-boot-verification.md)에 있습니다.

| Task | 상태 | 실제 결과 |
| --- | --- | --- |
| 1 공식 생성·빌드 | 완료 | Initializr Kotlin 2.3.21·Boot 4.1.1·Wrapper 9.7.1, JDK 25, strict lock |
| 2 설정·DI·no-db | 완료 | constructor DI, native 18093 health/greeting, 예약 404 |
| 3 HTTP·Problem | 완료 | typed DTO, 정확한 missing/null/type 422와 전역 오류 계약 |
| 4 H2·Flyway·JPA | 완료 | 독립 file, migration/validate, ordinary entity와 nullable repository |
| 5 transaction | 완료 | 실제 proxy, claim flush, rollback 뒤 fresh read, commit 뒤 응답 |
| 6 경합·멱등 | 완료 | 실제 H2 connection/JVM의 replay/conflict/stock/rollback/isolation |
| 7 관측·수명 | 완료 | JSON logs, request context, 실제 완료 metrics, SIGTERM/lock 반환 |
| 8 전체 수락 | 완료 | 기존 Java 35개 + Kotlin 실제 경계 3개 = 38개 통과, production Java 0개 |
| 9 독립 검토 | 완료 | 책임·Java parity·Kotlin 경계 재검토, 발견 5건 수정, 38개 전체 시험·native 재시작 재검증 |
| 10 공유 문서 통합 | 완료 | 공용 진입점·MkDocs 상태 문구 갱신, strict build 성공 |
| 11 container 판단 | 후속 | 18094만 예약, 미구현 |

## Task 1. 공식 Kotlin 프로젝트 생성과 빌드 기준 고정

목표:
공식 Spring Initializr로 JDK 25·Gradle Kotlin DSL Kotlin 앱을 만들고 생성 결과를 검토한 뒤 필요한 빌드 입력만 조정합니다.

예상 결과:
- `kotlin/spring-boot/`에 package `com.backendtemplate`, Kotlin production main, `.java-version` 25, Wrapper 9.7.1이 존재함
- 구현 시점 공식 metadata/생성물로 Boot와 Kotlin plugin 호환 버전이 다시 확인되고 선택 근거가 기록됨
- `kotlin-jvm`, `kotlin-spring`, `kotlin-jpa`, `kotlin-reflect`, Jackson Kotlin module과 MVC/JPA/Flyway/H2/Actuator가 정합함
- H2 console이 제거되고 Prometheus·Springdoc, compiler flags, strict dependency lock이 검토된 상태임
- clean test와 bootJar가 strict lock으로 통과하며 production Java source가 0개임

## Task 2. 설정·DI·인사와 DB 없는 시작

목표:
Kotlin primary constructor `private val` DI, UTC `Clock`, 설정 검증, greetings/health와 빈 DB URL의 정상 no-db 조립을 구현합니다.

예상 결과:
- native `127.0.0.1:18093`에서 root·greetings·live/ready·docs·metrics가 DB 없이 응답함
- DB URL이 비면 DataSource/Flyway/JPA와 예약 Bean·route가 없고 readiness가 healthy임
- 잘못된 environment·pool 설정은 요청 수신 전 시작 실패이며 부분 시작에서 획득한 자원이 닫힘
- fixed `Clock` Kotlin unit test와 실제 no-db HTTP/lifecycle/shutdown 시험이 통과함

## Task 3. Kotlin HTTP DTO와 Problem 계약

목표:
불변 `data class` DTO/contract와 top-level 입력 검증, 예약 전용 Jackson deserializer, 전역 custom exception 번역을 구현합니다.

예상 결과:
- 성공 `data` envelope, health/metrics/docs/204/file/stream 예외, 404·405·409·422·500·503 Problem 계약이 Java와 일치함
- `product_id` missing은 `REQUIRED`, null·number·boolean·array·object는 `INVALID`, unknown/non-object/malformed body는 422임
- `Allow`, `Retry-After`, content type, 32자리 server request ID와 공개 field location/code가 보존됨
- 일반 경계의 `!!`, nullable/default 입력 흡수, 오류 원문·민감 입력 노출이 0개임

## Task 4. 별도 H2 file·Flyway·ordinary JPA entity

목표:
Java와 같은 schema 의미를 Kotlin 앱의 독립 H2 file에 구성하고 ordinary entity와 nullable Spring Data repository를 구현합니다.

예상 결과:
- `kotlin/spring-boot/data/`와 임시 시험 경로가 Java runtime data와 분리됨
- Flyway가 schema를 단독 소유하고 Hibernate `validate`, `open-in-view=false`, H2 console 비활성이 적용됨
- `plugin.jpa` synthetic no-arg와 entity all-open을 통해 source-level 가짜 기본값 없이 persist/load/lazy reference가 동작함
- entity는 `data class`가 아니고 repositories 밖으로 노출되지 않으며 nullable miss는 `T?`로 표현됨
- migration 반복·기존 결과 보존·schema mismatch 시작 실패 시험이 통과함

## Task 5. 예약 transaction·rollback·fresh read

목표:
public Kotlin Service proxy에 예약 원자성을 두고 claim flush, 조건부 재고 차감, 예약/replay 저장과 rollback 뒤 재조회 순서를 구현합니다.

예상 결과:
- `@Service`와 `kotlin-spring` 적용으로 실제 class proxy가 존재하고 default-final 때문에 transaction이 우회되지 않음
- 신규 성공은 commit 뒤에만 Controller로 반환되고 checked/unchecked/constraint/commit 실패에서 claim·stock·reservation·replay가 함께 원복됨
- 동일 key unique 충돌만 `IdempotencyClaimed`로 번역되고 실패 transaction 종료 뒤 새 proxy read가 저장된 결과를 반환함
- Repository는 commit·업무 오류 결정을 소유하지 않고 Service가 조회·순수 validation·변경 순서를 소유함
- Base/Facade/base repository/범용 transaction wrapper 없이 `ReservationAttempts`의 실제 복구 책임만 존재함

## Task 6. 실제 H2 경합·멱등성·isolation

목표:
transaction test 자동 rollback이 아닌 실제 H2 commit과 독립 연결·JVM으로 예약 불변조건과 실패 복구를 검증합니다.

예상 결과:
- 동일 key 병렬 요청의 효과가 1회이고 같은 body는 원래 ID·시각 replay, 다른 body는 409 conflict임
- 다른 key 경쟁에서 stock이 음수가 아니며 stock 수와 성공 예약 수가 일치함
- 잠긴 상품/key가 독립 상품/key를 불필요하게 막지 않고 lock timeout 뒤 재시도가 성공함
- 저장 실패·commit 실패·rollback 경계 실패에서 최종 claim/stock/reservation/replay count가 기대값과 일치함
- embedded file 재시작과 독립 JVM 시험에서 원래 결과 보존, oversell 방지, rollback 뒤 fresh read가 확인됨

## Task 7. 로그·metrics·특수 응답과 수명

목표:
Java 계약과 같은 안전한 JSON logging, 요청 문맥, 실제 transaction 완료 metrics, graceful shutdown을 Kotlin으로 구현합니다.

예상 결과:
- request ID가 header/body/log에서 일치하고 MDC가 성공·실패·async 완료 뒤 정리됨
- `http.completed`가 한 번만 기록되고 raw query/body/key/예외 메시지·stack trace가 노출되지 않음
- transaction `committed/rolled_back/failed`가 manager 완료 callback과 실제 DB 상태에 일치하고 계측 실패가 업무 결과를 바꾸지 않음
- committed stream 오류에 Problem body가 덧붙지 않고 204·file·429·error dispatch header/body 계약이 유지됨
- SIGTERM 중 진행 요청 완료, 유한 종료와 H2 file lock 반환이 실제 process 시험으로 확인됨

## Task 8. Java 35개 harness 이식과 전체 수락

목표:
기존 Java Spring Boot의 35개 동작 시나리오를 Kotlin 앱에서 재사용 또는 이식하고 Kotlin 고유 회귀 시험을 더해 전체 기준선을 확정합니다.

예상 결과:
- 기존 35개 시나리오가 누락 없이 대응표를 가지며 HTTP/DB/process/fault harness는 필요 시 `src/test/java`에서 실행됨
- DTO/Jackson null·proxy/final·JPA no-arg/all-open의 실제 경계 시험은 `src/test/kotlin`에 존재함
- production application source가 모두 Kotlin이고 test Java 재사용 범위와 interop 수정이 명시됨
- Java test 호환을 위한 production accessor/wrapper가 없고 Java callsite가 Kotlin getter에 맞게 적응됨
- Java 25에서 strict locked `clean test bootJar`가 실패·오류·skip 0으로 통과함
- native 18093의 no-db와 별도 file DB seed→reserve→restart→replay 결과 및 남은 미검증 범위가 기록됨

## Task 9. 독립 검토·구현 수정·최종 검증

목표:
구현자가 아닌 독립 reviewer가 설계·Java parity·Kotlin 관용성·실제 실패 증거를 검토하고 발견 사항을 수정한 뒤 전체 검증을 다시 실행합니다.

예상 결과:
- reviewer가 책임 경계, proxy/final, null/Jackson, JPA plugin, transaction/fresh read, actual H2 상태를 대조한 기록이 존재함
- 발견 사항마다 수정 또는 근거 있는 비수정 결정이 연결되고 미해결 high-impact 항목이 0개임
- 수정 후 strict locked 전체 test/bootJar와 native no-db·file DB smoke가 다시 통과함
- planned/verified 상태, 실제 test 수, 명령, 결과와 남은 제한이 최종 verification 문서에 정확히 기록됨

## Task 10. 공유 문서 discoverability 통합 — coordinator 소유

목표:
Kotlin 구현과 독립 검토가 수락된 뒤 coordinator가 저장소 공용 진입점과 MkDocs 탐색 경로를 실제 상태에 맞게 연결합니다.

예상 결과:
- 루트 README, [구현 색인](README.md), 구현 README/verification과 MkDocs nav에서 Kotlin sibling을 찾을 수 있음
- 구현 전 계획 문구가 실제 verified 범위로 갱신되고 Java·Rails 설명이나 포트 표와 모순이 없음
- MkDocs strict build와 Mermaid 렌더링이 warning 없이 통과함
- 공유 문서 변경은 현재 design worker의 세 파일과 분리되어 coordinator가 검토·반영함

## Task 11. 후속 container 통합 판단

목표:
native 구현 수락 뒤에만 container/Compose 통합을 별도 wave로 결정합니다.

예상 결과:
- Task 1–10 완료 시점에도 Dockerfile·Compose·공유 monitoring 설정은 변경되지 않음
- 공유 README/MkDocs에는 native verified 범위와 container 미구현 상태만 정확히 표시됨
- 후속 통합 시 게시 포트 18094와 독립 volume/project 이름을 쓰는 결정이 유지됨
- container build, non-root 실행, healthcheck, data persistence, 수집기 연결은 구현 전 상태로 명확히 남음

## 구현 순서와 편집 규칙

Task 1→5가 최소 기능 경로이고 Task 6→8이 구현 증거, Task 9가 독립 수락, Task 10이 공용 탐색 통합을 완성합니다.
Task 11 container 통합은 이번 구현 wave의 완료 조건이 아닙니다.
공식 생성·Wrapper·Flyway·Gradle lock이 제공하는 작업은 해당 공식 command를 사용합니다.
그 뒤의 source/config/document 수동 변경은 exact-match `apply_patch`로만 수행하고 shell substitution·heredoc write를 사용하지 않습니다.
Rails 파일과 Java production 구현, 공통 설계·Compose는 이 task 문서의 변경 범위가 아닙니다.
