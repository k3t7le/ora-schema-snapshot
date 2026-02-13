# ora-schema-snapshot

Oracle 스키마 DDL을 스냅샷으로 저장하는 Python 도구입니다.

## 특징
- `DBMS_METADATA.GET_DDL` 기반 추출
- 환경 의존 DDL 정규화(STORAGE/TABLESPACE/파티션 인스턴스 라인 제거)
- 스냅샷 파일 동기화(A/M/D)
- 변경(diff) 있을 때만 Git commit/push
- 마이그레이션 기능 없음(스냅샷 전용)
- DDL 감사 로그를 `_audit/<service>/<owner>/<type>/<object>.jsonl`로 증분 저장

## 설치
```bash
pip install -e .
```

## 실행
```bash
python -m orasnap.cli dry-run --config config/snapshot.yml
python -m orasnap.cli snapshot --config config/snapshot.yml
```

## 설정 파일
예시는 `config/snapshot.example.yml` 참고.

주요 항목:
- `oracle`: 접속 정보
- `scope`: include/exclude/object_types
- `output.snapshot_root`: 스냅샷 저장 루트
- `git.repo_path`: Git 저장소 로컬 경로
- `logs.retention_days`: 로그 보관 일수
- `audit`: DDL 감사 로그 JSONL 내보내기 설정
  - `audit.state_file` 기본 저장 위치: 프로젝트 루트 (`.orasnap_audit_state.json`)

## SQL 사전 설치
사전 설치 스크립트:
- `docs/sql/PRE_INSTALL.sql`

포함 내용:
- `ORASNAP_SVC` 계정 생성
- 메타 추출/감사 트리거 권한 부여
- `DDL_AUDIT_LOG`, `TRG_DDL_AUDIT_DB` 생성
