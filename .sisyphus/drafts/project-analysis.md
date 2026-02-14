# Project Analysis: ora-schema-snapshot

최종 분석 시점: 2026-02-14

## 문서 대상
이 문서는 2가지 관점을 동시에 커버합니다.

1) 개발자(온보딩/개발/유지보수)
- 설치/실행/설정/구조/테스트/확장 포인트

2) 운영/보안(권한/감사/데이터/리스크)
- Oracle 계정/권한 범위, 감사 로그 저장/상태 파일, Git 자동 push, 운영 배치 시 주의사항

권장 읽기 순서:
- 개발자: 1 → 3 → 4 → 7 → 9 → 6
- 운영/보안: 1 → 8 → 6(감사/Git) → 10

## 1) 한 줄 요약
Oracle DB의 스키마 DDL을 `DBMS_METADATA.GET_DDL`로 추출한 뒤, 환경 의존 요소를 정규화해서 파일 스냅샷으로 저장하고(추가/수정/삭제 동기화), 변경이 있을 때만 Git commit/push까지 수행하는 Python CLI 도구입니다. 마이그레이션 도구는 아닙니다(스냅샷 전용).

## 2) 핵심 특징/요구사항(README 기반)
- DDL 추출: `DBMS_METADATA.GET_DDL` 기반
- DDL 정규화: `STORAGE`/`TABLESPACE` 제거 + 파티션 인스턴스 라인 제거
- 스냅샷 파일 동기화: A/M/D(added/modified/deleted)
- Git 자동화: 변경(diff) 있을 때만 commit, 옵션으로 push
- 감사 로그: `_audit/<service>/<owner>/<type>/<object>.jsonl`로 증분 JSONL 저장
- 마이그레이션 기능 없음

참고: `README.md`

## 3) 기술 스택 / 패키징
- Runtime: Python >= 3.11 (`pyproject.toml`)
- Packaging: setuptools (`pyproject.toml`)
- Dependencies: `PyYAML`, `oracledb`
- Dev deps: `pytest`
- CLI 엔트리포인트:
  - `orasnap` (console script): `orasnap.cli:main` (`pyproject.toml`)
  - `python -m orasnap` (모듈 실행): `src/orasnap/__main__.py`

## 4) 실행 방법(개발자 Quickstart)
설치:
```bash
pip install -e .
```

실행:
```bash
python -m orasnap.cli dry-run --config config/snapshot.yml
python -m orasnap.cli snapshot --config config/snapshot.yml

# 또는
orasnap dry-run --config config/snapshot.yml
orasnap snapshot --config config/snapshot.yml
```

CLI 출력(요약): `src/orasnap/cli.py`
- extracted / failed / written / deleted / unchanged / audit_exported / committed / pushed / log_file / commit_sha / failures

## 5) 프로젝트 구조(중요 파일만)
- `src/orasnap/cli.py`
  - argparse 기반 CLI (`snapshot`, `dry-run`)
  - `run_snapshot(config, dry_run=...)` 호출
- `src/orasnap/pipeline.py`
  - 전체 파이프라인 오케스트레이션
  - 로그 파일 생성/retention 적용
  - 감사 상태 파일 경로(project root 기준) 결정
  - (dry-run 제외) Git stage/commit/push 수행
- `src/orasnap/config.py`
  - YAML config 로딩/검증 및 `AppConfig` dataclass 모델
- `src/orasnap/oracle/extractor.py`
  - Oracle 객체 탐색(ALL_OBJECTS) + GET_DDL 추출(벌크 + fallback)
  - TABLE의 경우: 테이블 DDL + 컬럼/테이블 코멘트 + 관련 인덱스 DDL을 하나로 묶어 저장
- `src/orasnap/normalize/ddl_normalizer.py`
  - 환경 의존 구문 제거/정리 + 라인 엔딩(LF/CRLF)
- `src/orasnap/store/writer.py`
  - 스냅샷 디렉토리에 `.sql` 파일을 원자적으로 쓰고, 불필요 파일은 삭제
- `src/orasnap/vcs/git_ops.py`
  - `git -C <repo_path>`로 stage/commit/push 수행
- `src/orasnap/oracle/audit_exporter.py`
  - 감사 테이블에서 신규 로그를 읽어 JSONL로 append + 상태 파일 업데이트

## 6) 동작 흐름(멘탈 모델)
진입점은 CLI 하나이며, 내부적으로는 단일 파이프라인 함수로 수렴합니다.

1) CLI
- `orasnap snapshot|dry-run --config ...`
- `src/orasnap/cli.py` → `src/orasnap/pipeline.py:run_snapshot()`

2) Config/Logging
- YAML을 `load_config()`로 읽어서 `AppConfig`로 변환 (`src/orasnap/config.py`)
- 로그 파일: `logs/orasnap-YYYYMMDD.log` (config가 `config/` 아래에 있으면 project root의 `logs/`를 사용)
- 로그 보관 정책: `logs.retention_days` (기본 30일)

3) Extraction (Oracle)
- `OracleMetadataExtractor.extract()` (`src/orasnap/oracle/extractor.py`)
- ALL_OBJECTS에서 대상 객체를 발견(스키마 include/exclude 및 object_types 기준)
- DDL은 우선 벌크 추출 시도 → 실패/누락만 개별 추출 fallback
- `DBMS_METADATA.SET_TRANSFORM_PARAM`로 SQL terminator/pretty 및 segment/storage/tablespace/partitioning 옵션 일부 비활성화

4) Normalize
- `DdlNormalizer.normalize()` (`src/orasnap/normalize/ddl_normalizer.py`)
- `STORAGE(...)` 및 `TABLESPACE ...` 제거
- 파티션 인스턴스 라인(`PARTITION ...`, `SUBPARTITION ...`) 제거
- 공백 라인 2개 이상 연속 축약, 라인 엔딩(LF/CRLF) 적용

5) Write snapshots (A/M/D 동기화)
- `SnapshotWriter.write(entries, dry_run=...)` (`src/orasnap/store/writer.py`)
- 저장 경로 규칙:
  - (현재 구현) `<snapshot_root>/<OWNER>/<OBJECT_TYPE>/<OBJECT_NAME>.sql`
  - OBJECT_TYPE은 공백을 `_`로 치환
  - 이름은 안전화: `[^A-Za-z0-9_.-]+` → `_` (최종적으로 빈 값이면 `unnamed`)
- 기존 파일과 내용이 동일하면 unchanged로 계산
- 더 이상 필요 없는 `.sql` 파일은 삭제 (desired set에 없는 기존 파일)

6) Audit export (옵션)
- 조건: `audit.enabled: true` AND `dry_run == false`
- 기본 audit root:
  - `audit.root`가 지정되면 그 경로
  - 없으면 `git.repo_path / "_audit"` (`src/orasnap/pipeline.py:_resolve_audit_root`)
- 저장 규칙: `_audit/<service>/<owner>/<type>/<object>.jsonl` (JSONL append)
- 상태 파일(state_file):
  - absolute면 그대로 사용
  - relative면 “project root(= config 상위, config 디렉토리면 그 부모)” 기준으로 resolve
  - 기본값: `.orasnap_audit_state.json`
- state key: `<SERVICE>::<DB_USERNAME>` (upper) (`src/orasnap/oracle/audit_exporter.py:_state_key`)
- 테이블 미존재(ORA-00942) 등은 warning 후 export 스킵

7) Git commit/push (옵션)
- 조건: `dry_run == false`
- `GitOps.commit_if_changed()` (`src/orasnap/vcs/git_ops.py`)
  - stage 대상 경로: 기본은 `output.snapshot_root`; audit root가 존재하면 audit root도 포함
  - staged diff가 없으면 commit/push 수행하지 않음
  - `auto_push: true`면 `git push <remote> <current-branch>`
- commit message (`src/orasnap/pipeline.py:_build_commit_message`):
  - `commit_message_template`의 `{timestamp}`를 local time ISO로 치환
  - A/M/D 파일 목록을 body에 포함(최대 30개, 초과는 `... (+N more)`)

## 7) 설정 파일 스키마(YAML)
예시: `config/snapshot.example.yml`

- `oracle`
  - host / port(기본 1521) / service_name / username / password
- `scope`
  - discovery_mode: 현재 `hybrid`만 허용
  - include_schemas / exclude_schemas / object_types
  - object_types 기본값은 `src/orasnap/config.py:DEFAULT_OBJECT_TYPES`
- `output`
  - snapshot_root: 스냅샷 저장 루트(Path, config 파일 위치 기준 resolve)
  - line_ending: `LF` 또는 `CRLF`
- `git`
  - repo_path: git repo 루트(Path, config 파일 위치 기준 resolve)
  - branch: null 가능(지정 시 현재 브랜치 검증)
  - commit_message_template: 기본 `snapshot: {timestamp}`
  - auto_push: 기본 true
  - remote: 기본 origin
- `logs`
  - retention_days: 기본 30
- `audit`
  - enabled: 기본 true
  - root: null이면 `git.repo_path/_audit`
  - table: 기본 `DDL_AUDIT_LOG`
  - state_file: 기본 `.orasnap_audit_state.json`

## 8) 사전 설치(SQL) / 운영 고려(운영/보안)
사전 설치 스크립트: `docs/sql/PRE_INSTALL.sql`

주요 내용:
- `ORASNAP_SVC` 계정 생성 및 권한 부여
  - `EXECUTE ON SYS.DBMS_METADATA`, `SELECT ANY DICTIONARY`, `SELECT_CATALOG_ROLE` 등
  - 스냅샷/감사 자동화를 위해 `SELECT ANY TABLE/SEQUENCE`, `EXECUTE ANY PROCEDURE/TYPE` 등 광범위 권한
- 감사 테이블 생성: `ORASNAP_SVC.DDL_AUDIT_LOG`
- DB 레벨 DDL 트리거 생성: `ORASNAP_SVC.TRG_DDL_AUDIT_DB`
  - 이벤트: CREATE/ALTER/DROP/TRUNCATE
  - 시스템 계정 관련 이벤트는 노이즈 방지 위해 제외 목록 적용

운영 메모(프로젝트 문서 기반): `PROJECT_CONTEXT.md`
- `audit.state_file`은 운영에서 영속 경로(절대경로) 권장
- 상태 파일 유실 시 감사 로그가 처음부터 재수집될 수 있음
- 코드 저장소(`ora-schema-snapshot`)와 결과 저장소(`snapshots` git repo) 분리 권장

## 9) 테스트/검증 현황
테스트 프레임워크: pytest (`pyproject.toml` optional dev)

실행:
```bash
python -m pytest -q
```

대표 유닛 테스트(패턴 확인용):
- `tests/unit/test_normalizer.py`: STORAGE/TABLESPACE 제거, 파티션 라인 제거, CRLF 처리
- `tests/unit/test_writer.py`: add/modify/unchanged/delete, dry-run 무쓰기
- `tests/unit/test_git_ops.py`: 변경 있을 때만 commit하는 동작
- `tests/unit/test_audit_exporter.py`: JSONL append 및 state 파일 업데이트, LOB read 타이밍(DPY-1001 회귀 방지)
- `tests/unit/test_extractor_bulk.py`: 벌크 추출 성공/실패/누락 시 fallback 대상 식별
- `tests/unit/test_pipeline_audit_state_path.py`: audit state_file 상대/절대 경로 resolve 규칙
- `tests/unit/test_commit_message.py`: commit message 변경 목록/길이 제한

CI: `.github/workflows/*`는 현재 발견되지 않았습니다(로컬 테스트 중심).

## 10) 리스크/주의점/개선 여지(운영/보안 관점 포함)
- Oracle 접근 권한 범위가 넓음: `PRE_INSTALL.sql`의 ANY 권한들은 운영에서 보안 검토 필요
- Oracle 계정은 전용 계정으로만 사용 권장(업무 계정 겸용 금지)
- DDL 정규화는 의도적으로 정보를 제거함:
  - TABLESPACE/STORAGE/파티션 인스턴스 제거는 환경 차이(diff noise) 줄이지만, 일부 스키마 재구성 용도로는 정보 손실
- 파일 경로 안전화(_safe_name)로 인해 실제 오브젝트명과 파일명이 1:1로 완전 동일하지 않을 수 있음(특수문자 치환)
- 감사 로그 export는 “append-only + state 기반”:
  - state file 깨짐/유실 시 중복 export 가능
  - audit table 스키마 변경 시 exporter SQL과 불일치 가능
- Git push는 기본 true:
  - 운영에서 원치 않으면 `git.auto_push: false`로 명시 권장

추가 변경 요구(문서 기준, 예정):
- 스냅샷 경로에 SERVICE 폴더를 추가하는 방향
  - 목표: `<snapshot_root>/<SERVICE>/<OWNER>/<OBJECT_TYPE>/<OBJECT>.sql`
  - 의미: `output.snapshot_root`를 서비스명을 제외한 베이스로 둘 수 있어 설정 혼동을 줄임
  - 호환/가드(사용자 결정): snapshot_root가 이미 서비스 폴더로 끝나면 중복 생성하지 않고 경고로 안내

운영에서 특히 민감한 설정 포인트:
- `audit.state_file`: 절대경로 + 백업/권한(쓰기 가능) 확보
- `git.repo_path`: 결과 저장소 위치(권한/remote/branch 정책) 명확화
- `oracle.password`: 내부망에서 관리자만 열람 가능하다면 평문 YAML을 repo에 포함하는 운영을 허용(사용자 결정)
  - 단, repo 접근 제어(권한/네트워크) + 파일 권한 통제(최소 권한)는 필수

운영 권장 설정(결정 반영):
```yaml
git:
  auto_push: true
  branch: "main"
  remote: "origin"
```

## 11) 참고 문서
- `README.md`
- `PROJECT_CONTEXT.md` (최근 변경/운영 메모 포함)
- `docs/plans/oracle-schema-snapshot-implementation-plan-ko.md`
- `docs/sql/PRE_INSTALL.sql`

## 12) 분석 범위/한계
- 본 분석은 정적 코드/문서 기반이며 실제 Oracle 연결/DDL 추출은 실행하지 않았습니다.
- 스냅샷 결과 저장소(`git.repo_path`)의 운영 규칙(브랜치/권한/remote)은 환경에 따라 달라질 수 있습니다.

## 다음 확인 질문
- 운영 환경에서 `git.auto_push`: **true**로 운영 (사용자 결정)
  - 운영 리스크가 커지는 대신 자동화가 단순해짐
  - 권장 보완: `git.branch`를 고정해서(예: main) 의도치 않은 브랜치로 push되는 사고를 줄이기
- `git.branch`: **main**으로 고정 (사용자 결정)
