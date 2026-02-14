# ora-schema-snapshot 기능/구조 개선 작업 계획

## TL;DR

> **Quick Summary**: 운영 안정성과 자동 push 리스크를 관리하면서, 개발/검증 흐름을 표준화(CI)하고, CLI/문서 정합성을 개선한다.
>
> **Deliverables**:
> - GitHub Actions CI(최소 `pytest`) 추가
> - CLI UX 개선(`--version`, 에러 메시지/exit code 명확화)
> - 문서 정합성(스냅샷 경로 규칙, 운영 runbook) 정리
> - 스냅샷 경로를 `<snapshot_root>/<SERVICE>/...`로 변경(서비스 폴더 자동 생성)
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: CI → snapshot path change

---

## Context

### Original Request
- 운영 runbook 1본 작성
- 기능/구조 개선을 위한 작업 계획 1본 작성

### Evidence (Repo 기반)
- README: Oracle DDL 스냅샷 도구(스냅샷 전용, 마이그레이션 아님), 감사 JSONL, 변경 시만 commit/push: `README.md`
- CLI: `snapshot`/`dry-run` + `run_snapshot()` 호출: `src/orasnap/cli.py`
- 파이프라인: extractor → normalizer → writer → audit exporter → git commit/push: `src/orasnap/pipeline.py`
- 설정 스키마: YAML → dataclass, Python 3.11+, deps(PyYAML, oracledb), pytest: `pyproject.toml`, `src/orasnap/config.py`
- 테스트 존재(유닛 위주): `tests/unit/*`
- CI 워크플로우 파일이 현재 없음: `.github/workflows/*` 없음

### Operational Policy (User Decision)
- Oracle 비밀번호는 내부망에서 관리자만 접근 가능한 범위에서는 평문 YAML을 repo에 포함하는 방식도 허용
  - 전제: repo 접근 제어(권한/네트워크)와 운영 절차로 통제

### 운영 결정(사용자)
- 운영에서 `git.auto_push=true`
- 운영 브랜치는 `main`으로 고정(`git.branch="main"` 권장)

### Metis Review (Key Guardrails)
- 스냅샷 전용(마이그레이션 기능 추가 금지)
- 히스토리 rewrite/비밀번호 회전 같은 “사고 대응”은 자동 실행 금지(명시적 요청 없으면 문서/가이드만)
- CI는 Oracle 연결 없이도 통과해야 함(테스트는 유닛 위주)
- Git push 실패/보호브랜치/동시 실행 등 운영 edge case를 runbook/검증에 포함

---

## Work Objectives

### Core Objective
운영에서 안전하게 반복 실행 가능한 스냅샷 도구로 유지하면서, CI/문서/CLI와 저장 레이아웃을 개선하여 운영 사고 위험과 유지보수 비용을 줄인다.

### Must Have
- CI에서 `pytest`가 Oracle 없이 통과
- `orasnap` 사용성과 실패 시 진단 가능성(명확한 메시지/exit code) 개선
- 스냅샷 결과가 서비스 단위로 자동 분리되도록 저장 경로 규칙 개선

### Must NOT Have (Guardrails)
- 마이그레이션(DDL 적용/롤백) 기능 추가 금지
- 기본값으로 외부 인프라(Vault/SSM 등) 의존 강제 금지(옵션으로만)
- 사용자 명시 요청 없이 Git 히스토리 rewrite 수행 금지

---

## Verification Strategy (MANDATORY)

> **UNIVERSAL RULE: ZERO HUMAN INTERVENTION**
>
> 이 계획의 모든 Acceptance Criteria는 에이전트가 명령 실행/파일 검증으로 자동 확인 가능해야 한다.
> 운영자가 DB에 접속해 수동 확인해야만 하는 검증은 “문서에 절차를 추가”로 대체한다.

### Test Decision
- **Infrastructure exists**: YES (`pytest`)
- **Automated tests**: Tests-after (변경과 함께 필요한 유닛/스모크 테스트 추가)
- **Framework**: pytest

### Agent-Executable Verification Commands (공통)
- `python -m pytest -q`
- `python -m orasnap.cli --help`
- `orasnap --help` (console script 환경에서)

---

## Execution Strategy

### Parallel Execution Waves

Wave 1 (Start Immediately):
- Task 1: GitHub Actions CI 골격 추가
- Task 2: CLI UX 개선(`--version`, 에러 메시지)

Wave 2 (After Wave 1):
- Task 3: 문서 정합성/운영 runbook 정리 및 docs 반영
- Task 4: 동시 실행 방지(락 파일) + 충돌 위험 문서화/감지(선택)
- Task 5: 스냅샷 저장 경로 변경(SERVICE 폴더 자동 생성) + 테스트/문서

Critical Path: Task 1 → Task 5 (레이아웃 변경)

---

## TODOs

> 각 Task는 “구현 + 검증(테스트/QA)”를 포함한다.

- [ ] 1. GitHub Actions CI 추가(pytest 스모크)

  **What to do**:
  - `.github/workflows/ci.yml` 추가
  - Python 3.11 이상에서 다음을 실행:
    - `pip install -e .[dev]`
    - `python -m pytest -q`
  - (선택) lint/format 단계 추가(현재 repo에는 설정이 없음)

  **Must NOT do**:
  - Oracle 연결을 요구하지 말 것(CI는 DB 없이 통과)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `pyproject.toml` - Python 버전/의존성/pytest dev deps
  - `tests/` - 테스트 존재

  **Acceptance Criteria (Agent-Executable)**:
  - [ ] `.github/workflows/ci.yml` 파일 존재
  - [ ] `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"` → `OK`
  - [ ] `python -m pytest -q` → PASS

  **Agent-Executed QA Scenarios**:
  ```
  Scenario: CI workflow file is valid YAML
    Tool: Bash
    Preconditions: PyYAML available (or install in the command)
    Steps:
      1. Run: python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"
      2. Assert: stdout contains OK
    Expected Result: workflow parses as YAML
    Evidence: .sisyphus/evidence/task-3-ci-yaml-parse.txt
  ```

- [ ] 2. CLI UX 개선: `--version` 및 에러 경로 진단성

  **What to do**:
  - `orasnap` CLI에 `--version` 추가
  - 치명 오류 시 stderr 메시지에 “어떤 설정/어떤 단계에서 실패했는지”가 드러나도록 개선
    - 최소: config 경로/명령(snapshot|dry-run) 표시
  - CLI help에 “snapshot only, no migration” 문구 유지

  **Must NOT do**:
  - 동작을 깨는 큰 리팩터링 금지(작은 UX 개선)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/orasnap/cli.py` - argparse 구성 및 main()
  - `pyproject.toml` - 패키지 버전(0.1.0)

  **Acceptance Criteria (Agent-Executable)**:
  - [ ] `python -m orasnap.cli --help` → exit code 0
  - [ ] `python -m orasnap.cli --version` → exit code 0, stdout에 버전 문자열 포함
  - [ ] `python -m pytest -q` → PASS

- [ ] 3. 문서 정합성/운영 문서 정리

  **What to do**:
  - 문서와 실제 구현이 어긋난 부분 정리
    - 예: 과거 계획 문서는 `snapshot_root/service_name/schema/...` 형태를 언급하나, 현재/목표 구현은 `<snapshot_root>/<SERVICE>/<OWNER>/<OBJECT_TYPE>/<OBJECT>.sql` 형태로 정리
  - 운영 runbook을 repo 문서 위치로 옮겨 공식화
    - 소스: `.sisyphus/drafts/ora-schema-snapshot-ops-runbook.md`
    - 타겟(권장): `docs/runbook/ops-runbook.md`
  - README에서 “예시 설정 사용 + 로컬 설정은 ignore”를 명확히 안내

  **Must NOT do**:
  - 출력 디렉토리 구조를 깨는 변경을 문서 없이 진행하지 말 것

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/orasnap/store/writer.py` - 실제 스냅샷 파일 경로 규칙
  - `docs/plans/oracle-schema-snapshot-implementation-plan-ko.md` - 과거 계획 문서(정합성 수정 대상)
  - `README.md` - 사용자-facing 문서
  - `.sisyphus/drafts/ora-schema-snapshot-ops-runbook.md` - 운영 runbook 초안

  **Acceptance Criteria (Agent-Executable)**:
  - [ ] `test -f docs/runbook/ops-runbook.md` → exit code 0
  - [ ] 문서 업데이트가 포함된 상태에서 `python -m pytest -q` → PASS

- [ ] 4. 동시 실행 방지(락 파일) + 파일명 충돌 리스크 완화

  **What to do**:
  - 파이프라인 실행 시작 시 “단일 실행 락”을 획득하고 종료 시 해제
    - 기본 락 위치(권장): logs 디렉토리 또는 project root 아래(예: `logs/orasnap.lock`)
    - 락 획득 실패 시: 명확한 오류 메시지 + non-zero exit
  - (선택) SnapshotWriter 경로 안전화로 인한 파일명 충돌 가능성에 대한 가드/경고
    - 최소: 충돌 가능성을 docs/runbook에 명시
    - 확장: 동일 경로로 매핑되는 객체가 발견되면 실패(데이터 손실 방지)

  **Must NOT do**:
  - 외부 락 서비스/추가 의존성을 기본으로 도입하지 말 것

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/orasnap/pipeline.py` - 파이프라인 실행 시작/종료 지점(락 획득/해제 삽입 위치)
  - `src/orasnap/store/writer.py` - 파일 경로 매핑 규칙과 안전화 로직(충돌 리스크 원천)
  - `.sisyphus/drafts/ora-schema-snapshot-ops-runbook.md` - 운영에서 동시 실행/충돌 대응 절차

  **Acceptance Criteria (Agent-Executable)**:
  - [ ] 락이 중복 실행을 차단하는 유닛 테스트가 추가됨
  - [ ] `python -m pytest -q` → PASS

- [ ] 5. 스냅샷 저장 경로 변경: SERVICE 폴더 자동 생성

  **What to do**:
  - 스냅샷 저장 경로 규칙을 다음으로 변경
    - 목표: `<output.snapshot_root>/<oracle.service_name>/<OWNER>/<OBJECT_TYPE>/<OBJECT>.sql`
    - 기존: `<output.snapshot_root>/<OWNER>/<OBJECT_TYPE>/<OBJECT>.sql`
  - 호환/가드(사용자 선택: 1번 정책)
    - `output.snapshot_root`가 이미 서비스 폴더로 끝나는 경우(예: `.../ORCLPDB`)에는 서비스 폴더를 "추가로" 만들지 않음
    - 대신 WARNING 로그로 알려주고, 권장 설정(서비스 제외 베이스 경로)을 안내
  - 설정/문서 업데이트
    - 사용자는 `output.snapshot_root`에 서비스명을 넣지 않아도 되도록 안내
    - 기존 설정이 이미 서비스명을 포함하고 있을 때 “중복 서비스 폴더”가 생기지 않도록 가드/경고/호환 정책을 적용
  - 테스트 업데이트
    - `tests/unit/test_writer.py`의 기대 경로 수정
    - (필요 시) 파이프라인 stage_paths가 서비스 하위까지 포함되도록 반영/테스트

  **Must NOT do**:
  - 서비스 폴더 중복 생성으로 경로가 바뀌어 “모든 파일이 삭제/재생성”되는 사고 유발 금지
  - 출력 레이아웃 변경을 문서/가이드 없이 배포하지 말 것

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential; output layout change)
  - **Blocks**: None
  - **Blocked By**: Task 3

  **References**:
  - `src/orasnap/store/writer.py` - `_entry_path()`가 저장 레이아웃을 결정
  - `src/orasnap/pipeline.py` - stage_paths(스냅샷 디렉토리)를 git add 대상으로 포함
  - `src/orasnap/config.py` - `OracleConfig.service_name`/`OutputConfig.snapshot_root`
  - `config/snapshot.example.yml` - 예시에서 snapshot_root 값을 서비스 제외 베이스로 안내해야 함
  - `README.md` - 실행/설정 설명 업데이트 필요
  - `docs/plans/oracle-schema-snapshot-implementation-plan-ko.md` - 경로 규칙 정합성 수정 대상
  - `tests/unit/test_writer.py` - writer 동작 기대치 업데이트

  **Acceptance Criteria (Agent-Executable)**:
  - [ ] `python -m pytest -q` → PASS
  - [ ] 유닛 테스트로 2가지 케이스가 검증됨
    - base root: `<root>/ORCLPDB/...` 생성
    - legacy root(끝이 ORCLPDB): `<root>/...`로 중복 생성이 되지 않음


---

## Decision Recorded

- Oracle 비밀번호는 내부망에서 관리자만 접근 가능한 범위에서는 평문 YAML을 repo에 포함하는 운영을 허용(사용자 결정).
- snapshot 경로 변경 시 호환/가드: `output.snapshot_root`가 이미 서비스명으로 끝나면 서비스 폴더를 중복 생성하지 않고 WARNING로 권장 설정을 안내(사용자 결정: 1번 정책).

---

## Commit Strategy

- 권장: 기능 단위로 1~2개의 커밋으로 묶기
  - `ci: add pytest workflow`
  - `feat(cli): add --version and improve error output`
  - `docs: add ops runbook and align snapshot path docs`
  - `feat(snapshot): write snapshots under <snapshot_root>/<service_name>/... with legacy guard`
  - `feat(pipeline): prevent concurrent runs with lock file`

---

## Success Criteria

### Verification Commands
```bash
python -m pytest -q
python -m orasnap.cli --help
python -m orasnap.cli --version
```

### Final Checklist
- [ ] CI에서 Oracle 없이 테스트 통과
- [ ] 운영 runbook이 정식 문서로 제공
- [ ] CLI 진단성 개선(--version 포함)
- [ ] 스냅샷 저장 경로가 `<snapshot_root>/<SERVICE>/...`로 정리되어 서비스별 충돌 위험이 줄어듦
