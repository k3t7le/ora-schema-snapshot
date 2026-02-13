-- =============================================================================
-- PRE_INSTALL.sql
-- 목적:
-- 1) ORASNAP 스냅샷/감사용 계정 생성
-- 2) DBMS_METADATA 기반 DDL 추출 권한 부여
-- 3) ANY 시스템 권한 기반 접근 권한 부여(객체별 GRANT 반복 제거)
-- 4) DDL 감사 테이블 + DB 레벨 DDL 트리거 생성
--
-- 중요:
-- - 아래 "수정 대상 값"을 먼저 원하는 값으로 변경한 뒤, 단계별로 직접 실행하세요.
--
-- 권장 실행 계정:
-- - SYS 또는 사용자/권한/트리거 생성이 가능한 관리자 계정
-- =============================================================================

-- =============================================================================
-- [수정 대상 값] (필요 시 아래 문자열을 전체 치환해서 사용)
--   ORASNAP_SVC         : 스냅샷/감사 계정명
--   StrongPassword_2026 : 계정 비밀번호
--   USERS               : 기본/감사 테이블스페이스
--   TEMP                : 임시 테이블스페이스
-- =============================================================================

SET SERVEROUTPUT ON

-- =============================================================================
-- STEP 1) 계정 생성
-- 실행 계정: SYS 또는 관리자
-- 참고: 이미 계정이 있으면 CREATE USER는 건너뛰세요.
-- 확인 쿼리: SELECT username FROM dba_users WHERE username = 'ORASNAP_SVC';
-- =============================================================================
CREATE USER ORASNAP_SVC
  IDENTIFIED BY "StrongPassword_2026"
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  ACCOUNT UNLOCK;

-- =============================================================================
-- STEP 2) 메타 추출/접속 기본 권한 부여
-- 실행 계정: SYS 또는 관리자
-- =============================================================================
GRANT CREATE SESSION TO ORASNAP_SVC;
GRANT EXECUTE ON SYS.DBMS_METADATA TO ORASNAP_SVC;
GRANT SELECT_CATALOG_ROLE TO ORASNAP_SVC;
GRANT SELECT ANY DICTIONARY TO ORASNAP_SVC;

-- 감사 로그 테이블 저장 quota: USERS 테이블스페이스 무제한
ALTER USER ORASNAP_SVC QUOTA UNLIMITED ON USERS;

-- =============================================================================
-- STEP 3) 객체별 GRANT 대신 ANY 시스템 권한 부여
-- 실행 계정: SYS 또는 관리자
-- 설명:
-- - 신규 객체가 생성되어도 별도 GRANT 재실행이 필요 없습니다.
-- - 권한 범위가 넓으므로 전용 계정(ORASNAP_SVC)으로만 사용하세요.
-- =============================================================================
GRANT SELECT ANY TABLE TO ORASNAP_SVC;
GRANT SELECT ANY SEQUENCE TO ORASNAP_SVC;
GRANT EXECUTE ANY PROCEDURE TO ORASNAP_SVC;
GRANT EXECUTE ANY TYPE TO ORASNAP_SVC;

-- =============================================================================
-- STEP 4) DDL 트리거 및 감사 테이블 생성을 위한 권한 부여
-- 실행 계정: SYS 또는 관리자
-- =============================================================================
GRANT CREATE TABLE TO ORASNAP_SVC;
GRANT CREATE TRIGGER TO ORASNAP_SVC;
GRANT ADMINISTER DATABASE TRIGGER TO ORASNAP_SVC;

-- =============================================================================
-- STEP 5) 감사 테이블 생성
-- 실행 계정: ORASNAP_SVC
-- 예시:
--   CONN ORASNAP_SVC/"StrongPassword_2026"@<HOST>:<PORT>/<SERVICE_NAME>
-- 참고: 이미 존재하면 CREATE TABLE은 건너뛰세요.
-- =============================================================================
CREATE TABLE ORASNAP_SVC.DDL_AUDIT_LOG (
  AUDIT_ID         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  EVENT_TIME       TIMESTAMP(6) WITH LOCAL TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  SYSEVENT         VARCHAR2(30) NOT NULL,
  DB_USER          VARCHAR2(128),
  LOGIN_USER       VARCHAR2(128),
  CURRENT_SCHEMA   VARCHAR2(128),
  OS_USER          VARCHAR2(255),
  HOST             VARCHAR2(255),
  IP_ADDRESS       VARCHAR2(64),
  MODULE           VARCHAR2(128),
  OBJ_OWNER        VARCHAR2(128),
  OBJ_TYPE         VARCHAR2(30),
  OBJ_NAME         VARCHAR2(261),
  SQL_TEXT         CLOB
) TABLESPACE USERS;

CREATE INDEX ORASNAP_SVC.IX_DDL_AUDIT_LOG_01
  ON ORASNAP_SVC.DDL_AUDIT_LOG (EVENT_TIME, OBJ_OWNER, OBJ_NAME)
  TABLESPACE USERS;

-- =============================================================================
-- STEP 6) DB 레벨 DDL 감사 트리거 생성
-- 실행 계정: ORASNAP_SVC
-- 기록 이벤트: CREATE, ALTER, DROP, TRUNCATE
-- 시스템 계정(SYS, SYSTEM, CTXSYS 등) 관련 DDL은 노이즈 방지를 위해 제외
-- =============================================================================
CREATE OR REPLACE TRIGGER ORASNAP_SVC.TRG_DDL_AUDIT_DB
AFTER DDL ON DATABASE
DECLARE
  PRAGMA AUTONOMOUS_TRANSACTION;
  l_sql_parts ORA_NAME_LIST_T;
  l_part_cnt  PLS_INTEGER;
  l_sql_text  CLOB;
BEGIN
  -- 감사 오브젝트 자기 자신은 제외
  IF ORA_DICT_OBJ_OWNER = 'ORASNAP_SVC'
     AND ORA_DICT_OBJ_NAME IN ('DDL_AUDIT_LOG', 'TRG_DDL_AUDIT_DB', 'IX_DDL_AUDIT_LOG_01')
  THEN
    RETURN;
  END IF;

  IF ORA_SYSEVENT NOT IN ('CREATE', 'ALTER', 'DROP', 'TRUNCATE') THEN
    RETURN;
  END IF;

  -- 시스템 계정 관련 DDL은 기록 제외 (필요 시 목록 조정)
  IF UPPER(NVL(ORA_DICT_OBJ_OWNER, '')) IN (
       'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'WMSYS',
       'ORDSYS', 'ORDDATA', 'OLAPSYS', 'LBACSYS', 'DVSYS',
       'OJVMSYS', 'AUDSYS', 'OUTLN', 'DBSNMP', 'APPQOSSYS'
     )
     OR UPPER(NVL(ORA_LOGIN_USER, '')) IN (
       'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'WMSYS',
       'ORDSYS', 'ORDDATA', 'OLAPSYS', 'LBACSYS', 'DVSYS',
       'OJVMSYS', 'AUDSYS', 'OUTLN', 'DBSNMP', 'APPQOSSYS'
     )
  THEN
    RETURN;
  END IF;

  l_part_cnt := ORA_SQL_TXT(l_sql_parts);
  IF l_part_cnt > 0 THEN
    FOR i IN 1 .. l_part_cnt LOOP
      l_sql_text := l_sql_text || l_sql_parts(i);
    END LOOP;
  END IF;

  INSERT INTO ORASNAP_SVC.DDL_AUDIT_LOG (
    EVENT_TIME,
    SYSEVENT,
    DB_USER,
    LOGIN_USER,
    CURRENT_SCHEMA,
    OS_USER,
    HOST,
    IP_ADDRESS,
    MODULE,
    OBJ_OWNER,
    OBJ_TYPE,
    OBJ_NAME,
    SQL_TEXT
  ) VALUES (
    SYSTIMESTAMP,
    ORA_SYSEVENT,
    SYS_CONTEXT('USERENV', 'SESSION_USER'),
    ORA_LOGIN_USER,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA'),
    SYS_CONTEXT('USERENV', 'OS_USER'),
    SYS_CONTEXT('USERENV', 'HOST'),
    SYS_CONTEXT('USERENV', 'IP_ADDRESS'),
    SYS_CONTEXT('USERENV', 'MODULE'),
    ORA_DICT_OBJ_OWNER,
    ORA_DICT_OBJ_TYPE,
    ORA_DICT_OBJ_NAME,
    l_sql_text
  );
  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
END;
/

-- =============================================================================
-- STEP 7) 점검 쿼리
-- 실행 계정: ORASNAP_SVC 또는 조회 가능한 계정
-- =============================================================================
SELECT owner, trigger_name, status
  FROM dba_triggers
 WHERE owner = 'ORASNAP_SVC'
   AND trigger_name = 'TRG_DDL_AUDIT_DB';

SELECT COUNT(*) AS audit_rows
  FROM ORASNAP_SVC.DDL_AUDIT_LOG;

-- =============================================================================
-- 완료
-- =============================================================================

