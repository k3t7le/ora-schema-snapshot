# PROJECT_CONTEXT

최종 업데이트: 2026-02-13

## 1) 프로젝트 목적
- 프로젝트명: `ora-schema-snapshot`
- Oracle DDL을 `DBMS_METADATA`로 추출해서 정규화 후 Git에 스냅샷 저장
- 마이그레이션 도구가 아닌 스냅샷 전용 도구

## 2) 현재 아키텍처/동작 흐름
1. `orasnap.cli` 명령 실행 (`dry-run` / `snapshot`)
2. `OracleMetadataExtractor`가 대상 객체 탐색 및 DDL 추출
3. `DdlNormalizer`로 저장/테이블스페이스/파티션 인스턴스 등 정규화
4. `SnapshotWriter`가 파일 A/M/D 동기화
5. `OracleAuditExporter`가 DDL 감사 로그를 `_audit`에 JSONL 증분 저장
6. 변경이 있을 때만 Git commit/push

## 3) 구현 완료 사항
- 테이블 DDL에 코멘트 + 인덱스 병합 저장 지원
- `audit` 설정 추가:
  - `enabled`
  - `root`
  - `table`
  - `state_file`
- `_audit/<service>/<owner>/<type>/<object>.jsonl` 구조로 저장
- 감사 증분 상태 파일 사용:
  - 기본: `.orasnap_audit_state.json`
  - 키 형식: `<SERVICE_NAME>::<DB_USERNAME>`
  - 값: 마지막 처리 `AUDIT_ID`
- 로그 기능:
  - 일자별 파일 `logs/orasnap-YYYYMMDD.log`
  - 보관 정책(`logs.retention_days`, 기본 30일)
- 커밋 메시지:
  - 로컬 시간 사용
  - 변경 파일 목록(A/M/D) 포함
  - 과도한 길이 방지 제한(최대 30개, 나머지 요약)

## 4) 2026-02-13 주요 수정 내역
- `DPY-4009` 수정:
  - 벌크 쿼리 positional bind 개수 불일치 해결
- 성능 개선:
  - 벌크 조회 + 실패 객체 개별 fallback
  - `OBJECT_NAME IN (...)` 청크 방식(`_bulk_chunk_size=500`)
  - 진행률 로그 추가(`Extraction progress: n/total`)
  - 단계별 소요시간 로그 추가(Extraction/Write/Audit/Git)
- `DPY-1001` 수정:
  - 감사 내보내기에서 LOB 직렬화를 DB 연결 종료 전에 수행하도록 변경
  - `OracleAuditExporter.export()` 연결 라이프사이클 정리

## 5) 문서/SQL
- 계획 문서: `docs/plans/oracle-schema-snapshot-implementation-plan-ko.md`
- 사전 설치: `docs/sql/PRE_INSTALL.sql`
  - 계정 `ORASNAP_SVC` 기준
  - 감사 테이블 `DDL_AUDIT_LOG`
  - DB DDL 트리거 `TRG_DDL_AUDIT_DB`
  - 이벤트: `CREATE/ALTER/DROP/TRUNCATE`
  - 시스템 계정 제외 방식 적용

## 6) 현재 설정(개발 환경 기준)
- `config/snapshot.yml`
  - Oracle 계정: `ORASNAP_SVC`
  - 포함 스키마: `HMES`, `ACETECH`, `EDIP`, `SFA_TEST`
  - `output.snapshot_root: D:/dev/snapshots/ORCLPDB`
  - `git.repo_path: D:/dev/snapshots`
  - `audit.enabled: true`

## 7) 실행 커맨드
- Dry-run:
  - `python -m orasnap.cli dry-run --config config/snapshot.yml`
- 실제 반영:
  - `python -m orasnap.cli snapshot --config config/snapshot.yml`

## 8) 최근 검증 결과
- 테스트:
  - `python -m pytest -q` 통과 (`16 passed`)
- 성능 관찰(현재 개발 DB 기준):
  - 대상 약 310개 객체 `dry-run` 추출 단계 약 103초
  - 쓰기 단계는 변경 없을 때 수 초 이내

## 9) 운영 반영 시 주의
- `audit.state_file`은 운영에서 영속 경로(절대경로) 권장
- 상태 파일 유실 시 감사 로그가 처음부터 재수집될 수 있음
- 코드 저장소(`ora-schema-snapshot`)와 결과 저장소(`snapshots`) 분리 권장

## 10) 협업 규칙
- 세션 종료 또는 주요 기능 변경 시 `PROJECT_CONTEXT.md` 갱신
- 다른 LLM/다음 세션은 본 문서 기준으로 이어서 작업
