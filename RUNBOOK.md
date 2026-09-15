# 템플릿으로 서비스 시작하기

새 저장소에 이 템플릿을 가져온 뒤 **구현 선택 → 기준 실행 → 서비스 설정 → 업무 추가 → 검증** 순서로 진행합니다.
설계 이유는 [design/](design/README.md), 실행 명령은 아래 구현별 가이드가 소유합니다.

## 1. 현재 범위를 확인하고 구현을 선택합니다

| 구현 | 작업 디렉터리 | 도구·로컬 DB | 현재 범위와 안내 |
| --- | --- | --- | --- |
| FastAPI | `python/fastapi/` | uv · SQLite | 전체 예약 계약 · [실행](design/implementations/quickstart.md) · [빌드·검증](python/fastapi/README.md) |
| FastAPI + FastCRUD | `python/fastapi-fastcrud/` | uv · SQLite/FastCRUD | 전체 예약 계약, 네이티브만 제공 · [실행·검증](python/fastapi-fastcrud/README.md) |
| NestJS | `ts/nestjs/` | pnpm · SQLite/Drizzle | 전체 예약 계약 · [실행·검증](ts/nestjs/README.md) |
| Spring Boot | `java/spring-boot/` | Gradle Wrapper · H2/JPA | 전체 예약 계약 · [실행·검증](java/spring-boot/README.md) |
| Kotlin Spring Boot | `kotlin/spring-boot/` | Gradle Kotlin DSL · H2/JPA | 전체 예약 계약 native 검증 완료, Compose 미구현 · [실행](kotlin/spring-boot/README.md) · [검증](design/implementations/kotlin-spring-boot-verification.md) |
| Rails | `ruby/rails/` | Bundler · SQLite/Active Record | 인사·health·조건부 재고 예약까지, 멱등성·metrics·Compose는 미구현 · [실행·검증](ruby/rails/README.md) |

Kotlin Spring Boot의 Task 1–10 구현·독립 검토·문서 통합, 38개 자동 시험과 native 18093 재시작 검증은 완료됐습니다.
container·Compose는 제공하지 않고 18094만 후속 게시 포트로 예약합니다.

처음에는 저장소 구조를 그대로 가져오고 선택한 구현만 실행합니다. 독립 프로젝트로 추출할 때는
해당 디렉터리의 소스·테스트·migration·스크립트·도구 버전 파일·lockfile을 함께 가져갑니다.
Dockerfile은 현재 제공하는 구현에서만 가져갑니다.
`.env`, 실제 DB, 빌드 결과와 개인 캐시는 가져오지 않습니다.
루트 Compose·스크립트·문서 링크는 현재 경로를 전제로 하므로 폴더를 옮기거나 다른 구현을 제거하면 함께 수정합니다.

## 2. 변경 전 기준 상태를 확인합니다

선택한 가이드의 고정 버전 도구로 설치·빌드·테스트를 수행하고 앱을 실행합니다.
DB 없는 실행을 지원하는 구현에서 그 경계를 먼저 확인한 뒤, 별도 로컬 DB에 migration·seed를 적용해
각 구현이 현재 제공하는 예약 범위까지 확인합니다.

- 공통으로 `/health/ready`와 정상·입력 오류 응답을 확인하고, docs endpoint는 각 가이드에 제공된 구현에서만 확인합니다.
- FastAPI, FastAPI + FastCRUD, NestJS, Java Spring Boot와 Kotlin Spring Boot는 DB 활성 후
  201 예약·같은 키 replay·`Idempotency-Replayed: true`를 확인합니다.
- 위 구현은 `/metrics`와 JSON 로그를 확인합니다. 수집 화면이 필요하면 [로컬 모니터링](design/implementations/local-monitoring.md)의 연결 대상인지 먼저 확인하며,
  Compose가 없는 Kotlin을 제공된 수집 대상으로 가정하지 않습니다.
- Rails는 조건부 재고 차감·예약 생성·조회만 확인하고, 멱등성·metrics·Compose 검증을 요구하지 않습니다.

기본 포트는 구현별 실행 가이드에 있습니다. 같은 템플릿으로 여러 서비스를 띄울 때는 포트뿐 아니라
Compose 프로젝트 이름·데이터 volume·모니터링 수집 대상도 서비스별로 구분합니다.

## 3. 서비스 이름과 환경을 맞춥니다

| 대상 | 변경할 내용 |
| --- | --- |
| 서비스 식별 | `APP_NAME`, `SERVICE_VERSION`, `APP_ENVIRONMENT`, README의 서비스 설명 |
| 실행 환경 | host·port, DB URL·자격 정보, pool·timeout, 로그 수준 |
| 코드 이름 | 필요할 때 Python `template_api`, Nest package 이름, Java/Kotlin `com.backendtemplate`와 Gradle group |
| 실행·관측 연결 | 패키지 import·진입점·빌드 경로, Compose 설정, Prometheus 대상·서비스 구분 |

각 구현의 `.env.example`을 설정 목록으로 사용하고 실제 비밀 값은 커밋하지 않습니다.
환경 파일의 자동 로딩 방식은 구현마다 다릅니다. 특히 NestJS·Spring Boot 네이티브 실행은 셸 환경으로 전달합니다.
중앙 Compose는 기본적으로 선택한 구현의 `.env.example`을 읽고, 별도 파일은 `BACKEND_ENV_FILE`로 지정합니다.
게시 포트는 현재 `scripts/compose.sh`가 지정하므로 `.env`만 바꾸면 된다고 가정하지 않습니다.

이름 변경은 필수 선행 작업이 아닙니다. 바꾼다면 코드·테스트·설정·스크립트의 참조를 함께 변경하고 다시 빌드합니다.
의존성·lockfile·생성 코드는 uv·pnpm·Gradle·프레임워크의 지원 명령으로 관리합니다.

## 4. 가장 작은 업무 하나를 연결합니다

인사 예제를 출발점으로 입력·업무·응답을 연결하고, 저장이 필요한 경우 repository와 DB 모델을 추가합니다.
공통 성공 응답·오류·DI·트랜잭션·로그 계약을 유지하며 역할별 폴더에 기능 이름으로 파일을 둡니다.

| 구현 | 파일 배치와 확장 기준 |
| --- | --- |
| FastAPI | [서비스 적용](design/implementations/service-guide.md) · [폴더와 역할](design/implementations/fastapi-structure.md) |
| FastAPI + FastCRUD | [구현 설계·저장 경계](design/implementations/fastapi-fastcrud.md) |
| NestJS | [폴더와 역할](design/implementations/nestjs-structure.md) · [구현 설계](design/implementations/nestjs.md) |
| Spring Boot | [폴더와 역할](design/implementations/spring-boot-structure.md) · [트랜잭션 내부 동작](design/implementations/spring-boot-internals.md) |
| Kotlin Spring Boot | [폴더와 역할](design/implementations/kotlin-spring-boot-structure.md) · [Kotlin 구현 설계](design/implementations/kotlin-spring-boot.md) |
| Rails | [폴더와 역할](design/implementations/rails-structure.md) · [구현 설계](design/implementations/rails.md) |

예약 예제는 실제 업무가 연결된 후 관련 API·seed·테스트·문서를 함께 교체합니다.
이미 적용된 migration은 수정하지 않고 새 migration으로 schema를 변경합니다.
실제 서비스의 멱등 키는 사용자·업무 범위, 보존 기간, 실패 후 재시도 정책을 별도로 정합니다.

## 5. 서비스의 첫 기능 완료를 확인합니다

- [ ] 새 DB 생성과 기존 DB upgrade가 모두 성공합니다.
- [ ] 정상 응답·입력 오류·업무 거절·중간 실패와 rollback을 검증합니다.
- [ ] 경쟁하는 쓰기는 독립 연결의 동시 요청으로 불변조건을 확인합니다.
- [ ] 선택한 구현이 멱등 처리를 제공하면 같은 키 재시도·다른 입력 충돌·재시작 후 재생을 확인합니다.
- [ ] 로그와 제공되는 metrics에 비밀 값이나 원시 멱등 키가 노출되지 않고 종료 시 자원이 정리됩니다.
- [ ] 실행·설정·검증 명령을 새 서비스 README에 맞추고 변경 단위로 커밋합니다.

여기까지는 로컬 서비스 개발의 기준입니다. 운영에 필요한 인증·권한, 배포·비밀 관리,
백업·복구, 경보·외부 수집은 서비스 요구에 따라 별도로 구성합니다.
PostgreSQL로 전환할 때는 드라이버뿐 아니라 schema·migration·경합·복구를 실제 PostgreSQL에서 다시 검증합니다.
