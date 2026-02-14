# 운영 Runbook: ora-schema-snapshot

최종 업데이트: 2026-02-14

## TL;DR

- 이 도구는 Oracle 스키마 DDL을 추출/정규화하여 “스냅샷 파일”로 저장하고, 변경이 있을 때만 Git commit/push까지 수행한다.
- 운영 핵심은 3가지다.
  - Oracle 전용 계정/권한(DDL 추출 + 감사 테이블/트리거 선택)
  - 스냅샷 결과 저장소(Git repo)와 로그/상태 파일 영속 경로
  - 자동 push를 켰다면(`git.auto_push=true`) 브랜치/자격증명/보호 정책을 반드시 고정한다.

중요 변경 방향(요구사항 반영):
- `output.snapshot_root`는 “서비스명을 제외한 베이스 경로”로 두고
- 스냅샷 저장 시 도구가 `oracle.service_name` 하위 폴더를 자동 생성하여 저장한다.
  - 예: `<snapshot_root>/<service>/<owner>/<type>/<object>.sql`

호환/가드 정책(사용자 결정: 1번):
- 만약 사용자가 기존처럼 `output.snapshot_root`에 이미 서비스 폴더를 포함해두었다면(예: `.../ORCLPDB`)
  - 도구는 `.../ORCLPDB/ORCLPDB/...`처럼 중복 폴더를 만들지 않고
  - 그대로 `.../ORCLPDB/<owner>/...`에 저장한다(대신 WARNING 로그로 권장 설정을 안내).

참고 분석 문서: `.sisyphus/drafts/project-analysis.md`

---

## 1) 구성요소(운영 관점)

운영에는 “2개의 저장소/디렉토리”를 분리해서 생각하는 것이 안전하다.

1) 코드 저장소
- `ora-schema-snapshot` (이 repo)
- 실행 바이너리/CLI: `orasnap` 또는 `python -m orasnap.cli`

2) 결과 저장소(Git repo)
- `git.repo_path`로 지정
- 스냅샷 파일(`output.snapshot_root`)과 감사 로그(`_audit/`)가 이 저장소 아래에 존재하도록 운영하는 것을 권장
- 결과 저장소는 “스냅샷 전용 브랜치/정책”을 따르는 것이 안전

스냅샷 디렉토리 레이아웃(변경 후 목표):
- `<snapshot_root>/<SERVICE>/<OWNER>/<OBJECT_TYPE>/<OBJECT_NAME>.sql`
- 예:
  - `D:/dev/snapshots/ORCLPDB/HMES/TABLE/T1.sql`

---

## 2) 보안/사고 대응(필수)

현재 repo에는 민감정보 유출 가능성이 있는 파일이 존재할 수 있다.

- `config/snapshot.yml`에 Oracle 비밀번호가 평문으로 포함되어 있을 수 있다.
- 이 파일이 원격 리모트로 push된 적이 있다면, “비밀번호 회전 + (선택) Git 히스토리 정리”를 사고 대응으로 취급해야 한다.

운영 표준(사용자 결정 반영):
- Oracle 비밀번호를 내부망에서 관리자만 접근 가능한 범위에서는 평문 YAML을 repo에 포함하는 운영을 허용한다.
  - 전제: repo 접근 제어(권한/네트워크) + 운영 절차(권한 점검/이관/백업)로 통제
  - 유출 의심 시: 즉시 비밀번호 회전(절차만 문서화; 자동화는 하지 않음)

대안(선택):
- Git ignore 되는 로컬 파일 + OS/배포 파이프라인의 Secret 주입
- 암호화된 비밀 저장소(Vault/SSM 등) + 런타임 주입(조직 정책 기반)

---

## 3) 사전 준비(Oracle)

### 3.1 전용 계정/권한
- 전용 계정(예: `ORASNAP_SVC`)을 사용한다.
- 최소 요구 권한은 DDL 추출용(`DBMS_METADATA`, dictionary 조회)과, 선택 사항인 감사 테이블/트리거 생성/조회 권한이다.

사전 설치 스크립트:
- `docs/sql/PRE_INSTALL.sql`

주의:
- 스크립트는 운영 편의를 위해 ANY 권한이 포함될 수 있다. 운영 보안 기준에 맞춰 반드시 검토/조정한다.

### 3.2 감사(Audit) 구성(선택)
- 감사 테이블: 기본 `DDL_AUDIT_LOG`
- 감사 트리거: DB 레벨 DDL 트리거(이벤트: CREATE/ALTER/DROP/TRUNCATE)
- 시스템 계정 이벤트는 노이즈 방지 위해 제외

감사 비활성 운영도 가능하다.
- `audit.enabled: false`

---

## 4) 사전 준비(호스트/런타임)

### 4.1 Python 환경
권장:
- Python 3.11+
- 가상환경(venv) 사용

설치:
```bash
pip install -e .
```

### 4.2 Git 환경
요구사항:
- `git` CLI 사용 가능
- `git.repo_path`는 Git 저장소여야 함
- 운영에서 자동 push를 쓰면, push 권한이 있는 자격증명(HTTPS 토큰/SSH 키)이 사전에 설정되어야 함

운영 권장(사용자 결정 반영):
- `git.auto_push: true`
- `git.branch: "main"` (브랜치 고정)

---

## 5) 설정 파일 운영 가이드

설정 예시:
- `config/snapshot.example.yml`

운영에서 권장하는 방식:
- 운영 정책에 따라 `config/snapshot.yml`을 repo에 포함할 수 있다(평문 YAML 허용).
  - 필수 전제: repo 접근 제어 + 파일 권한/경로 통제(예: 전용 디렉토리 + 최소 권한)
  - 권장(리눅스 예): `chmod 600 /etc/orasnap/snapshot.yml`
- `audit.state_file`은 영속 경로(절대경로)를 권장한다(상태 유실 시 감사 로그가 처음부터 재수집될 수 있음).

핵심 설정 항목:
- `oracle`: 접속 정보
- `scope`: include/exclude/object_types
- `output.snapshot_root`: 스냅샷 파일 저장 베이스(서비스 폴더는 도구가 생성)
- `git.repo_path`: 결과 저장소(Git repo) 경로
- `git.branch`: 운영 브랜치 고정 권장(예: main)
- `logs.retention_days`: 로그 보관 일수
- `audit.enabled`, `audit.root`, `audit.table`, `audit.state_file`

---

## 6) 실행(운영 표준 절차)

### 6.1 Dry-run (권장: 배포 직후/장애 시)
목적:
- DB 접속/권한/대상 범위를 빠르게 점검
- 파일/Git 변경 없이 추출/정규화만 수행

```bash
orasnap dry-run --config /path/to/snapshot.yml
# 또는
python -m orasnap.cli dry-run --config /path/to/snapshot.yml
```

확인 포인트(출력 요약):
- `extracted`가 0이 아닌지
- `failed`가 0인지(0이 아니면 failures 목록 확인)
- `log_file` 경로가 기대 위치인지

### 6.2 Snapshot (정상 운영)
```bash
orasnap snapshot --config /path/to/snapshot.yml
```

확인 포인트:
- `written`/`deleted`/`unchanged` 수치가 기대 범위인지
- 감사 사용 시 `audit_exported`가 비정상적으로 폭증하지 않는지
- 변경이 있을 때만 `committed=true`가 되는지
- `auto_push=true` 운영이면 `pushed=true`인지

---

## 7) 스케줄링(예시)

중요 원칙:
- “동시 실행”을 피한다(중복 실행은 파일/상태 파일/Git에 영향).
- 실행 워킹디렉토리와 `git.repo_path`가 일관되게 설정되도록 한다.

### 7.1 Linux cron (예시)
```cron
*/30 * * * * /usr/bin/env -i HOME=/home/orasnap PATH=/usr/bin:/bin \
  /opt/orasnap/venv/bin/orasnap snapshot --config /etc/orasnap/snapshot.yml \
  >> /var/log/orasnap/cron.log 2>&1
```

### 7.2 Windows Task Scheduler (개념 예시)
- Action: `python`
- Arguments: `-m orasnap.cli snapshot --config C:\orasnap\snapshot.yml`
- Start in: `C:\orasnap\repo` (또는 코드 저장소 경로)

---

## 8) 모니터링/알림(가이드)

권장 알림 조건(예시):
- `failed > 0`
- `extracted == 0` (대상 범위 문제/권한 문제 가능)
- `committed=false`가 장기간 지속(대상 변경이 전혀 없다면 정상일 수 있음)
- `pushed=false`인데 `auto_push=true` (Git 인증/보호브랜치/네트워크 문제 가능)

로그 위치:
- `logs/orasnap-YYYYMMDD.log` (config 위치가 `config/` 아래면 project root의 `logs/`)
- 로그 보관: `logs.retention_days`

---

## 9) 장애 대응 / 트러블슈팅

### 9.1 Oracle 연결/권한
증상:
- 접속 실패, 권한 부족(ORA-xxxxx)

조치:
- `docs/sql/PRE_INSTALL.sql`의 권한 부여 부분 재검토
- DBMS_METADATA 실행 권한 및 dictionary 조회 권한 확인

### 9.2 감사 테이블 미존재(ORA-00942)
증상:
- 감사 export 스킵 경고

조치:
- 감사 기능이 필요하면 `PRE_INSTALL.sql`로 테이블/트리거 생성
- 감사가 불필요하면 `audit.enabled: false`로 비활성

### 9.3 Git push 실패
증상:
- `pushed=false`, GitError 메시지

조치:
- push 인증(SSH key/토큰) 확인
- 보호 브랜치 정책 확인(main direct push 금지 여부)
- 원격 리포지토리의 non-fast-forward 여부 확인
- 필요 시 `git.auto_push=false`로 완화 후 원인 분석

### 9.4 파일/경로 문제
증상:
- 경로 생성 실패, 권한 오류, 파일명 충돌

조치:
- `output.snapshot_root` 권한/드라이브/마운트 상태 확인
- 서비스 폴더 중복 생성(예: `<snapshot_root>`에 이미 `ORCLPDB`를 포함) 여부 확인
- 오브젝트명이 파일명으로 안전화되는 과정에서 충돌 가능(특수문자/대소문자)
- 충돌이 의심되면 해당 owner/type 경로에서 파일명 중복 여부 점검

---

## 10) 복구/롤백

- 스냅샷 결과는 Git 히스토리로 복구 가능(결과 저장소에서 checkout/restore).
- 감사 상태 파일(`audit.state_file`) 유실 시:
  - 감사 JSONL가 중복 append될 수 있으므로(재수집), 상태 파일 백업/권한을 점검.
- 부분 실패/중단 후에는 동일 명령 재실행이 기본 복구 수단이다(스냅샷은 덮어쓰기/삭제 동기화).

---

## 11) 운영 체크리스트(간단)

- [ ] Oracle 전용 계정/권한 검증 완료
- [ ] `git.repo_path`가 Git 저장소이며 push 자격증명 구성 완료
- [ ] `git.branch` 고정(main) 및 보호정책 확인
- [ ] `audit.state_file` 영속 경로(절대경로) 지정 및 백업 계획 수립
- [ ] 운영 설정 파일(repo 포함 시) 접근 권한/네트워크 범위가 정책에 부합함
- [ ] 운영 설정 파일 권한 최소화(예: 600) 적용
- [ ] dry-run 정상(실패 0) 확인 후 snapshot 운영 전환
