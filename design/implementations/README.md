# 구현별 설계 안내

공통 Backend 계약을 각 언어·프레임워크에서 실현하는 방법과 실제 검증 범위를 소유합니다.
공통 계약은 [Backend](../backend.md), [개발 원칙](../engineering.md), [관측](../observability.md),
[Runtime Review](../runtime-review.md)를 참조합니다.
[루트 README](../../README.md)에서 전체 범위로, [템플릿 적용 Runbook](../../RUNBOOK.md)에서
공통 적용 순서로 돌아갈 수 있습니다.

[예약 코드 책임 정리](responsibility-cleanup.md)는 기존 개발·검증 규칙에 대한 검토와 구현별 상태를 담습니다.
승인된 NestJS·FastAPI·Spring Boot·Rails 책임 정리 항목은 구현별 검증 기록과 함께 완료했습니다.

[트랜잭션 실행 책임](transaction-boundaries.md)은 Python 두 앱의 구현 결과와 NestJS·Rails 후속 제안을 구분합니다.

## 현재 제공 범위

추가 준비 중인 [Prisma·Rails 작업 단계](prisma-rails-tasks.md)는 구현 완료 범위와 구분합니다.
[FastAPI + FastCRUD 변형](fastapi-fastcrud.md)은 현재 FastAPI 기준선을 바꾸지 않는
두 번째 독립 Python 선택지로 구현했습니다. 네이티브 실행만 제공하며 Compose는 아직 연결하지 않았습니다.

Rails의 최소 API 작업은 [사용 안내](../../ruby/rails/README.md) · [설계](rails.md) ·
[구조](rails-structure.md) · [Task](rails-tasks.md) · [검증](rails-verification.md)에서 확인합니다.
예약 생성·조회와 조건부 재고 차감을 구현했으며, 검증 완료된 다섯 구현과 달리
멱등성·관측·Compose는 아직 후속 범위입니다.

Kotlin Spring Boot는 Java 앱을 대체하거나 호출하지 않는 sibling입니다.
[native 실행 안내](../../kotlin/spring-boot/README.md) · [구현 설계](kotlin-spring-boot.md) ·
[구조](kotlin-spring-boot-structure.md) · [Task](kotlin-spring-boot-tasks.md) · [검증](kotlin-spring-boot-verification.md)에서
Task 1–10 구현·독립 검토·문서 통합, 38개 자동 시험과 native 18093 재시작 결과를 확인할 수 있습니다.
native 범위는 수락했으며 Docker·Compose는 미구현입니다.

| 구현 | 실행 | 설계·구조 | 작업·검증 |
| --- | --- | --- | --- |
| Python / FastAPI | [로컬 실행](quickstart.md) · [환경·명령](../../python/fastapi/README.md) | [설계](fastapi.md) · [구조](fastapi-structure.md) | [Task](fastapi-tasks.md) · [검증](fastapi-verification.md) |
| Python / FastAPI + FastCRUD | [환경·명령](../../python/fastapi-fastcrud/README.md) | [설계·구조](fastapi-fastcrud.md#구현-구조와-구성-요소) | [작업·검증](fastapi-fastcrud.md#구현검증-상태) |
| TypeScript / NestJS | [사용 안내](../../ts/nestjs/README.md) | [설계](nestjs.md) · [구조](nestjs-structure.md) | [Task](nestjs-tasks.md) · [검증](nestjs-verification.md) |
| Java / Spring Boot | [사용 안내](../../java/spring-boot/README.md) | [내부 동작](spring-boot-internals.md) · [설계](spring-boot.md) · [구조](spring-boot-structure.md) | [Task](spring-boot-tasks.md) · [검증](spring-boot-verification.md) |
| Kotlin / Spring Boot | [native 실행](../../kotlin/spring-boot/README.md) | [설계](kotlin-spring-boot.md) · [구조](kotlin-spring-boot-structure.md) | [Task](kotlin-spring-boot-tasks.md) · [검증](kotlin-spring-boot-verification.md) |
| Ruby / Rails | [native 실행](../../ruby/rails/README.md) | [설계](rails.md) · [구조](rails-structure.md) | [Task](rails-tasks.md) · [검증](rails-verification.md) |

FastCRUD 변형과 Kotlin sibling을 포함한 검증 완료 다섯 구현은 설정·DI·초기화/종료·health·응답 계약·로그·metrics와
한정 수량 예약의 동시성·멱등성 예제를 제공합니다.
이 다섯 구현은 DB를 설정하지 않으면 예약 기능을 등록하지 않습니다.
실행한 시험과 구현별 제한은 각 검증 기록에서 확인합니다.

| 선택 | FastAPI | FastAPI + FastCRUD | NestJS | Spring Boot | Kotlin Spring Boot |
| --- | --- | --- | --- | --- | --- |
| 프로젝트 | `python/fastapi/` | `python/fastapi-fastcrud/` | `ts/nestjs/` | `java/spring-boot/` | `kotlin/spring-boot/` |
| 생성·의존성 도구 | uv | uv | Nest CLI·pnpm | Spring Initializr·Gradle Wrapper | Spring Initializr·Gradle Kotlin DSL |
| DI | dependency layer·Depends | dependency layer·Depends | 생성자·Provider·주입 토큰 | 생성자·Bean·transaction proxy | primary constructor·Bean·transaction proxy |
| 첫 DB | SQLite | SQLite | SQLite | H2 file | 별도 H2 file |
| DB 접근·migration | SQLAlchemy Core·Alembic | FastCRUD·SQLAlchemy ORM·Alembic | Drizzle·worker의 better-sqlite3·Drizzle Kit | Spring Data JPA·Hibernate·Hikari·Flyway | Spring Data JPA·Hibernate·Hikari·Flyway |
| 업무 transaction | Service의 `@transactional` | Service의 `@transactional` | Service의 transaction callback | public Service의 @Transactional | public Kotlin Service의 @Transactional |

응답 의미·업무 원자성·자원 수명은 맞추고 프레임워크의 파일 배치·실행 모델까지 동일하게 강제하지 않습니다.
SQLite의 쓰기 직렬화와 H2의 키별/행별 경합은 다른 구현입니다.
Spring HTTP 처리 지표와 FastAPI·NestJS 전송 경계 지표도 같은 뜻으로 합산하지 않습니다.

실제 서비스에 기능을 붙이는 방법은 각 사용 안내에 있습니다.
[FastAPI 서비스 적용](service-guide.md)은 Python 파일을 가져가는 구체적인 순서를 소유합니다.
PostgreSQL·Replica·sharding·인증·운영 수집 SDK·운영 부하는 후속 범위입니다.
Rust는 후보이며 빈 프로젝트를 만들지 않았습니다.

## 로컬 포트 배정

포트와 공유 실행 조정은 이 표가 소유합니다. 실행 직전에 실제 점유를 확인합니다.

| 대상 | 네이티브 게시 | 컨테이너 게시 | 컨테이너 내부 |
| --- | --- | --- | --- |
| FastAPI | 18080 | 18081 | 8000 |
| FastAPI + FastCRUD | 18092 | — (미통합) | — (미통합) |
| NestJS | 18083 | 18084 | 3000 |
| Spring Boot | 18085 | 18086 | 8080 |
| Kotlin Spring Boot | 18093 (native 검증) | 18094 (예약·미구현) | — (미구현) |
| Rails 최소 API | 18088 | 18089 (예약·미통합) | 3000 (예정) |
| MkDocs | 18090 | — | — |
| Prometheus | — | 19090 | 9090 |
| Grafana | — | 13000 | 3000 |

게시 주소는 `127.0.0.1`입니다. `18082`는 기존 FastAPI 임시 DB 모니터링 시험용으로 남깁니다.
시험 서버는 OS 임시 포트와 격리 데이터를 사용합니다.
`compose.yaml` 하나와 `scripts/compose.sh`로 통합된 구현을 선택하고 데이터 볼륨은 구현별로 구분합니다.
Kotlin Spring Boot는 이 Compose 경로에 없으며 18094는 후속 container 통합을 위한 예약입니다.
Prometheus·Grafana 한 세트를 공유하는 방법은 [로컬 모니터링](local-monitoring.md)을 따릅니다.
