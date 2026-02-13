from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from orasnap.config import OracleConfig
from orasnap.oracle import audit_exporter
from orasnap.oracle.audit_exporter import OracleAuditExporter


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows
        self.executed_sql = ""
        self.executed_binds: list[object] = []

    def execute(self, sql: str, binds: list[object]) -> None:
        self.executed_sql = sql
        self.executed_binds = binds

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._cursor = _FakeCursor(rows)
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


class _FakeOracleDb:
    def __init__(
        self,
        rows: list[tuple[object, ...]] | Callable[[_FakeConnection], list[tuple[object, ...]]],
    ) -> None:
        self._rows = rows
        self.connection: _FakeConnection | None = None

    def connect(self, **_: object) -> _FakeConnection:
        if callable(self._rows):
            self.connection = _FakeConnection([])
            self.connection._cursor._rows = self._rows(self.connection)
        else:
            self.connection = _FakeConnection(self._rows)
        return self.connection


class _FakeLob:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> str:
        return self._payload


class _ConnBoundLob:
    def __init__(self, payload: str, connection: _FakeConnection) -> None:
        self._payload = payload
        self._connection = connection

    def read(self) -> str:
        if self._connection.closed:
            raise RuntimeError("DPY-1001: not connected to database")
        return self._payload


def test_audit_exporter_writes_jsonl_and_state(tmp_path: Path, monkeypatch) -> None:
    rows = [
        (
            101,
            datetime(2026, 2, 13, 14, 15, 16),
            "ALTER",
            "HMES",
            "HMES",
            "HMES",
            "windows",
            "pc1",
            "192.168.0.10",
            "SQL Developer",
            "HMES",
            "TABLE",
            "T_LS1",
            _FakeLob("ALTER TABLE HMES.T_LS1 ADD COL1 NUMBER"),
        )
    ]
    monkeypatch.setattr(audit_exporter, "oracledb", _FakeOracleDb(rows))

    oracle_config = OracleConfig(
        host="127.0.0.1",
        port=1521,
        service_name="ORCLPDB",
        username="orasnap_svc",
        password="pw",
    )
    audit_root = tmp_path / "_audit"
    state_path = tmp_path / "logs" / "audit_state.json"

    exporter = OracleAuditExporter(
        oracle_config=oracle_config,
        service_name="ORCLPDB",
        audit_root=audit_root,
        state_path=state_path,
        table_name="DDL_AUDIT_LOG",
    )
    result = exporter.export(dry_run=False)

    assert result.exported_count == 1
    assert len(result.added_files) == 1
    assert len(result.modified_files) == 0

    output_file = audit_root / "ORCLPDB" / "HMES" / "TABLE" / "T_LS1.jsonl"
    assert output_file.exists()
    payload = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(payload) == 1
    record = json.loads(payload[0])
    assert record["audit_id"] == 101
    assert record["sysevent"] == "ALTER"
    assert record["obj_owner"] == "HMES"
    assert record["obj_type"] == "TABLE"
    assert record["obj_name"] == "T_LS1"
    assert "ALTER TABLE HMES.T_LS1" in record["sql_text"]

    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["ORCLPDB::ORASNAP_SVC"] == 101


def test_audit_exporter_reads_lob_before_connection_close(tmp_path: Path, monkeypatch) -> None:
    oracle_db = _FakeOracleDb(
        lambda conn: [
            (
                102,
                datetime(2026, 2, 13, 14, 30, 0),
                "ALTER",
                "HMES",
                "HMES",
                "HMES",
                "windows",
                "pc1",
                "192.168.0.10",
                "SQL Developer",
                "HMES",
                "TABLE",
                "T_TEST",
                _ConnBoundLob("ALTER TABLE HMES.T_TEST ADD C1 NUMBER", conn),
            )
        ]
    )
    monkeypatch.setattr(audit_exporter, "oracledb", oracle_db)

    oracle_config = OracleConfig(
        host="127.0.0.1",
        port=1521,
        service_name="ORCLPDB",
        username="orasnap_svc",
        password="pw",
    )
    audit_root = tmp_path / "_audit"
    state_path = tmp_path / "logs" / "audit_state.json"

    exporter = OracleAuditExporter(
        oracle_config=oracle_config,
        service_name="ORCLPDB",
        audit_root=audit_root,
        state_path=state_path,
        table_name="DDL_AUDIT_LOG",
    )
    result = exporter.export(dry_run=False)

    assert result.exported_count == 1
    output_file = audit_root / "ORCLPDB" / "HMES" / "TABLE" / "T_TEST.jsonl"
    record = json.loads(output_file.read_text(encoding="utf-8").strip())
    assert "ALTER TABLE HMES.T_TEST" in record["sql_text"]
