from __future__ import annotations

from orasnap.normalize.ddl_normalizer import DdlNormalizer


def test_normalizer_removes_storage_and_tablespace() -> None:
    ddl = """
CREATE TABLE "HMES"."T1" (
  "ID" NUMBER
) STORAGE (INITIAL 65536 NEXT 1048576)
TABLESPACE "HMES_SPACE";
""".strip()

    normalized = DdlNormalizer("LF").normalize(ddl)

    assert "STORAGE" not in normalized.upper()
    assert "TABLESPACE" not in normalized.upper()
    assert normalized.endswith("\n")


def test_normalizer_removes_partition_instance_lines() -> None:
    ddl = """
CREATE TABLE T_PART (
  ID NUMBER
)
PARTITION BY RANGE (ID)
(
  PARTITION P1 VALUES LESS THAN (10),
  PARTITION PMAX VALUES LESS THAN (MAXVALUE)
);
""".strip()

    normalized = DdlNormalizer("LF").normalize(ddl)

    assert "PARTITION BY RANGE" in normalized
    assert "PARTITION P1" not in normalized.upper()
    assert "PARTITION PMAX" not in normalized.upper()


def test_normalizer_respects_crlf() -> None:
    ddl = "CREATE TABLE T1 (ID NUMBER);\n"
    normalized = DdlNormalizer("CRLF").normalize(ddl)
    assert "\r\n" in normalized
    assert normalized.endswith("\r\n")

