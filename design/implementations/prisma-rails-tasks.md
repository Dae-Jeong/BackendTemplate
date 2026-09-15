# Prisma·Rails 준비와 구현 단계

Status: Rails Task 1–2 완료 · Prisma 적용 방식 선택 대기 · 2026-09-15

목표는 NestJS에서 Prisma를 사용하고 Rails의 관용적인 API 개발을 경험하면서 기존 응답·트랜잭션·동시성·멱등성 계약을 비교하는 것입니다.
NestJS의 기존 Drizzle 교체와 별도 비교 앱 추가 중 어느 방식인지는 사용자 선택 대기입니다.
Rails는 `ruby/rails/`의 API 전용 앱·Active Record·SQLite로 시작합니다.
사용자 지정 `gpt-5.6-sol` Orca 에이전트가 구현하고 중앙 에이전트가 범위·검증·통합을 관리합니다.
첫 구현 범위는 버전·공식 scaffold·인사·health·요청 시험이며 예약·관측·Compose는 후속 단계입니다.
Rails 최소 앱과 중앙 리뷰 보완을 완료했습니다. 실제 버전·13개 테스트·네이티브 실행 증거는
[Rails 검증 기록](rails-verification.md)에 있습니다. 다음은 Rails의 예약 schema·migration·transaction 단계입니다.

## Task 1. 실행 방식과 저장 경계 확정

목표: Prisma 적용 범위와 Rails 초기 구조, 도구 버전·포트·DB 경계를 정합니다.

예상 결과:

- Nest 교체/추가 방식과 기존 DB·Drizzle migration 이력의 보존 방안이 정해짐
- Prisma SQLite adapter의 실행 방식·transaction·잠금 대기·계측 가능 범위를 확인한 작은 실험 결과가 있음
- Rails의 `app/controllers`, `app/models`, `app/services`, `test`, `db/migrate` 책임과 명시적 의존성 전달 방식이 정해짐
- 호환되는 안정 버전을 CLI로 확인하고 프로젝트 버전 파일·lockfile에 고정할 준비가 됨

현재 Nest는 Drizzle·worker·tarn pool을 함께 사용합니다. Prisma Client가 Promise를 반환한다는 이유만으로
SQLite 실행이 이벤트 루프를 막지 않는다고 가정하지 않습니다. ORM 전환 시 현재 pool·worker를 그대로 감싸거나 제거하기 전에 실험합니다.
Rails에서는 Active Record의 모델·조회 기능을 사용하고 여러 저장 작업의 순서·트랜잭션에 필요한 Service만 추가합니다.
모든 모델을 감싸는 빈 Repository나 DI 컨테이너를 선행 도입하지 않습니다.

## Task 2. 가장 작은 앱 실행

목표: 공식 도구로 Prisma 기반 설정과 Rails API 앱을 준비하고 실행 진입점을 연결합니다.

예상 결과:

- Nest의 Prisma CLI 초기화·Client 생성과 격리 DB 연결 시험이 통과함
- Rails 공식 `rails new --api` 생성물을 바탕으로 인사·health API와 요청 시험이 동작함
- Ruby·Bundler는 시스템 Ruby와 분리해 사용하고 `.ruby-version`·Gemfile·lockfile로 관리됨
- 각 앱의 환경 예시·실행 명령과 실제 사용 포트가 기록됨

현재 셸의 Ruby는 2.6.10입니다. 이 시스템 Ruby를 변경하지 않습니다.
18087은 확인 시 이미 Java 프로세스가 사용 중이므로 Rails용으로 배정하지 않습니다.
포트는 구현 직전에 실제 점유를 다시 확인하고 [포트 정본](README.md#로컬-포트-배정)에 등록합니다.

## Task 3. 저장과 트랜잭션

목표: 단일 Primary·migration·seed·예약 저장을 연결합니다.

예상 결과:

- 새 DB와 기존 데이터 보존/이관 시나리오의 검증 결과가 있음
- Prisma transaction callback과 Rails Active Record transaction이 성공한 뒤에만 성공 응답함
- unique 제약·조건부 재고 차감·멱등 결과 저장을 하나의 transaction에서 처리함
- 실패 transaction을 종료한 뒤 충돌 재생을 처리하며, 잠금/획득 timeout과 업무 거절을 구분함

## Task 4. 공통 계약과 관측

목표: 공개 응답·오류·로그·metrics·시작/종료를 기존 계약에 맞춥니다.

예상 결과:

- `data` 성공 응답·Problem 오류·health/metrics 예외 형식의 HTTP 시험이 통과함
- 비밀 값·원시 키를 제외한 로그와 HTTP·DB 지표를 확인함
- 라이브러리에서 관측할 수 없는 pool/commit 결과는 추정 지표로 대체하지 않고 차이를 기록함
- 연결 종료·readiness와 DB 미설정 동작을 확인함

## Task 5. 경합 검증과 Compose 통합

목표: 독립 연결·프로세스의 예약 경합과 복구를 검증하고 공통 로컬 실행에 연결합니다.

예상 결과:

- 초과 판매 없음, 동일 키 동일 결과, 다른 입력 충돌, 실패 후 rollback, 재시작 후 재생이 검증됨
- 기존 Nest HTTP 계약이 유지되고 변경한 DB 시험의 대체 근거가 남음
- 중앙 Compose·선택 스크립트·공유 모니터링·MkDocs·Runbook에서 구현을 찾고 실행할 수 있음
- task별 검증·커밋·push가 완료됨

## 공식 근거

2026-09-15 확인. 명령·옵션과 버전 호환성은 실제 설치 시 다시 확인합니다.

- [Prisma SQLite 시작](https://docs.prisma.io/docs/prisma-orm/quickstart/sqlite): 공식 CLI·Client·SQLite adapter 구성
- [기존 SQLite 프로젝트에 Prisma 추가](https://docs.prisma.io/docs/prisma-orm/add-to-existing-project/sqlite): 기존 DB 도입 절차
- [Rails API 전용 앱](https://guides.rubyonrails.org/api_app.html): API generator·Controller·middleware 구성
- [Active Record transactions](https://api.rubyonrails.org/classes/ActiveRecord/Transactions/ClassMethods.html): transaction과 예외·callback 경계
