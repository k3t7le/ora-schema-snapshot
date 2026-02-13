# PROJECT_CONTEXT

## 1) 프로젝트 개요
- 프로젝트명: `ora-schema-snapshot`
- 목적: Oracle 스키마 DDL을 `DBMS_METADATA`로 추출해 정규화 후 Git에 스냅샷 저장
- 성격: 마이그레이션 도구가 아닌 **스냅샷 전용 도구**

## 2) 최근 합의된 운영 방식
- 추출 계정/감사 계정 통합: `ORASNAP_SVC` (단일 계정 사용)
- 권한 방식: 객체별 GRANT 반복 대신 `ANY` 권한 방식 사용
- 감사 트리거: `AFTER DDL ON DATABASE`
  - 기록 이벤트: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`
  - 시스템 계정(`SYS`, `SYSTEM`, `CTXSYS` 등) 관련 DDL 제외
- 테이블스페이스 quota:
  - `ORASNAP_SVC` on `USERS`: `QUOTA UNLIMITED`

## 3) 문서 상태 (현재 복원됨)
- 구현 계획서:
  - `docs/plans/oracle-schema-snapshot-implementation-plan-ko.md`
- 사전 설치 SQL:
  - `docs/sql/PRE_INSTALL.sql`

## 4) PRE_INSTALL.sql 핵심 포함 내용
- 스냅샷/감사 계정 생성 (`ORASNAP_SVC`)
- DDL 추출 권한:
  - `CREATE SESSION`
  - `EXECUTE ON SYS.DBMS_METADATA`
  - `SELECT_CATALOG_ROLE`
  - `SELECT ANY DICTIONARY`
  - `SELECT ANY TABLE`
  - `SELECT ANY SEQUENCE`
  - `EXECUTE ANY PROCEDURE`
  - `EXECUTE ANY TYPE`
- 감사 오브젝트 권한:
  - `CREATE TABLE`
  - `CREATE TRIGGER`
  - `ADMINISTER DATABASE TRIGGER`
- 감사 테이블:
  - `ORASNAP_SVC.DDL_AUDIT_LOG`
- 감사 트리거:
  - `ORASNAP_SVC.TRG_DDL_AUDIT_DB`

## 5) 구성 파일 상태 (현재 복원됨)
- `config/snapshot.yml`
- `config/snapshot.example.yml`

## 6) 실행/운영 참고
- 코드 실행 기본:
  - `python -m orasnap.cli dry-run --config config/snapshot.yml`
  - `python -m orasnap.cli snapshot --config config/snapshot.yml`
- Git 저장소는 로컬 경로를 의미함(원격 URL 아님)
- snapshot/git 저장소 예시:
  - `output.snapshot_root: D:/dev/snapshots/ORCLPDB`
  - `git.repo_path: D:/dev/snapshots`

## 7) 현 시점 점검 결과
- 소스/테스트/문서/설정 파일 복원 완료:
  - `src/orasnap/*.py`
  - `tests/unit/*.py`
  - `README.md`, `pyproject.toml`, `PROJECT_CONTEXT.md`
  - `docs/plans/*`, `docs/sql/PRE_INSTALL.sql`, `config/*.yml`
- 검증:
  - `python -m compileall src tests` 성공
  - `python -m pytest -q` 결과: `9 passed`
  - `python -m orasnap.cli --help` 정상 출력
