# Oracle Schema Snapshot Tool 구현 로드맵 (Python)

## 1. 목표
- Oracle 스키마의 DDL을 주기적으로 스냅샷하여 Git 이력으로 관리한다.
- `DBMS_METADATA` 기반으로 추출하고, 환경 의존 구문(스토리지/테이블스페이스/파티션 인스턴스)은 정규화한다.
- 변경(diff)이 있을 때만 Git commit/push 한다.
- 본 도구는 마이그레이션 도구가 아닌 **스냅샷 전용 도구**로 한정한다.

## 2. 범위와 비범위
- 범위:
  - 객체 탐색, DDL 추출, 정규화, 파일 동기화, Git 자동화
  - 실행 로그 보관 및 운영 설정 파일 관리
  - DDL 감사 테이블/트리거 기반 운영 추적(선택)
- 비범위:
  - 스키마 변경 배포, 롤백, 버전 업그레이드 자동 적용
  - 데이터 마이그레이션

## 3. 표준 아키텍처
- `orasnap.cli`: `dry-run`, `snapshot` 명령 제공
- `orasnap.oracle.extractor`: 객체 목록 조회 + `DBMS_METADATA.GET_DDL`
- `orasnap.normalize.ddl_normalizer`: 불필요 옵션 제거
- `orasnap.store.writer`: 스냅샷 파일 반영(A/M/D)
- `orasnap.vcs.git_ops`: 변경 감지 후 commit/push
- `orasnap.pipeline`: 전체 흐름 오케스트레이션 + 로깅

## 4. 단계별 구현 계획

### STEP 0. 환경/구조 준비
- Python 3.11+ 기준 패키지 구조 구성(`src/orasnap`)
- 설정 파일(`config/snapshot.yml`) 스키마 정의
- 실행 진입점(`python -m orasnap.cli`) 구성

### STEP 1. Oracle 연결과 객체 탐색
- `oracledb` 드라이버 연결
- `ALL_OBJECTS` 기반 객체 목록 조회
- 포함/제외 스키마, 객체 타입 필터 적용
- `TABLE`/`INDEX` 번들 저장 정책(테이블 파일 내 인덱스 병합) 적용

### STEP 2. DDL 추출
- 세션 트랜스폼 설정:
  - `SQLTERMINATOR=TRUE`, `PRETTY=TRUE`
  - `SEGMENT_ATTRIBUTES=FALSE`, `STORAGE=FALSE`, `TABLESPACE=FALSE`, `PARTITIONING=FALSE`
- `DBMS_METADATA.GET_DDL` 호출 실패 시 경고 로그로 수집
- TABLE 객체는 코멘트(`ALL_TAB_COMMENTS`, `ALL_COL_COMMENTS`)와 인덱스 DDL 병합

### STEP 3. 정규화
- 라인 엔딩 통일(`LF`/`CRLF`)
- 환경 종속 구문 제거:
  - STORAGE/PCTFREE/INITRANS 등 물리 옵션
  - TABLESPACE 절
  - 파티션 인스턴스성 표현
- 파일 간 불필요 diff 최소화를 위해 공백/줄바꿈 정리

### STEP 4. 스냅샷 파일 동기화
- 경로 규칙: `snapshot_root/service_name/schema/object_type/object_name.sql`
- 새 파일/수정/삭제 감지 후 동기화
- 결과 집계: `added`, `modified`, `deleted`, `unchanged`

### STEP 5. Git 연동
- Git repo 유효성 검증
- 변경 없으면 commit/push 생략
- 변경 있을 때만 commit
  - 커밋 메시지: 로컬 시간 사용
  - 파일 목록 포함(`A/M/D` prefix), 길이 과다 시 요약
- 설정 시 자동 push 수행

### STEP 6. 로그 및 운영성
- 로그 파일: `logs/orasnap-YYYYMMDD.log` (일자 단위)
- 보관 정책: `logs.retention_days` (기본 30일, 설정 가능)
- 실행 요약 출력: extracted/failed/written/deleted/committed/pushed

### STEP 7. 사전 설치(SQL) 표준화
- `docs/sql/PRE_INSTALL.sql` 제공
  - 스냅샷 계정 생성
  - DDL 추출 권한 부여(ANY 방식)
  - 감사 테이블/트리거 생성
- 트리거 정책:
  - 이벤트: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`
  - 시스템 계정(`SYS`, `SYSTEM`, `CTXSYS` 등) 제외

### STEP 8. 검증 시나리오
- `dry-run` 시 객체 개수/추출 오류 확인
- `snapshot` 2회 연속 실행:
  - 1회차: 파일 생성 + commit
  - 2회차(변경 없음): no-op, commit 없음
- DB 객체 변경 후 재실행:
  - 해당 객체 파일만 변경되는지 확인
  - commit 메시지 A/M/D 분류 확인

## 5. 운영 권장사항
- 스냅샷 전용 계정(`ORASNAP_SVC`) 분리 운영
- Git 저장소는 스냅샷 전용 repo/브랜치 권장
- DB별 설정 파일 분리 운영 권장(추적/장애 분리 용이)
- 감사 로그 테이블은 주기 purge 정책 병행 권장

## 6. 완료 기준 (Definition of Done)
- `dry-run`, `snapshot` 정상 동작
- 정규화된 DDL 산출물 재현 가능
- diff 있을 때만 Git commit/push
- 로그 파일 일자별 생성 및 보관정책 동작
- PRE_INSTALL.sql만으로 계정/권한/감사 트리거 초기 세팅 가능

