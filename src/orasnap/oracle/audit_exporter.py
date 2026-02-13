from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orasnap.config import OracleConfig

try:
    import oracledb
except ImportError:  # pragma: no cover - covered by runtime integration.
    oracledb = None


SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
TABLE_NAME_PATTERN = re.compile(r'^[A-Za-z0-9_$#."]+$')


@dataclass(frozen=True)
class AuditExportResult:
    exported_count: int
    added_files: list[Path]
    modified_files: list[Path]


class OracleAuditExporter:
    def __init__(
        self,
        oracle_config: OracleConfig,
        service_name: str,
        audit_root: Path,
        state_path: Path,
        table_name: str = "DDL_AUDIT_LOG",
        logger: logging.Logger | None = None,
    ) -> None:
        self.oracle_config = oracle_config
        self.service_name = service_name
        self.audit_root = audit_root
        self.state_path = state_path
        self.table_name = table_name
        self.logger = logger or logging.getLogger(__name__)

    def _require_driver(self) -> None:
        if oracledb is None:
            raise RuntimeError(
                "oracledb package is required. Install dependencies first: pip install -e ."
            )

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = SAFE_NAME_PATTERN.sub("_", value.strip())
        return cleaned.strip("_") or "UNKNOWN"

    def _state_key(self) -> str:
        return f"{self.service_name.upper()}::{self.oracle_config.username.upper()}"

    def _load_state(self) -> dict[str, int]:
        if not self.state_path.exists():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive path.
            self.logger.warning("Audit state file read failed: %s (%s)", self.state_path, exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        state: dict[str, int] = {}
        for key, value in raw.items():
            try:
                state[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return state

    def _save_state(self, state: dict[str, int]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _serialize(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "read"):
            try:
                value = value.read()
            except Exception:
                return str(value)
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                return bytes(value).decode("utf-8")
            except Exception:
                return bytes(value).decode("utf-8", errors="replace")
        if isinstance(value, (list, tuple)):
            return [OracleAuditExporter._serialize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): OracleAuditExporter._serialize(item) for key, item in value.items()}
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return str(value)

    def _validate_table_name(self) -> str:
        table = self.table_name.strip()
        if not table:
            return "DDL_AUDIT_LOG"
        if not TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid audit table name: {table}")
        return table

    def _fetch_rows(self, cursor: "oracledb.Cursor", last_audit_id: int) -> list[tuple[Any, ...]]:
        table = self._validate_table_name()
        sql = f"""
            SELECT
                AUDIT_ID,
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
            FROM {table}
            WHERE AUDIT_ID > :1
            ORDER BY AUDIT_ID
        """
        cursor.execute(sql, [last_audit_id])
        return cursor.fetchall()

    def export(self, dry_run: bool = False) -> AuditExportResult:
        self._require_driver()

        state = self._load_state()
        key = self._state_key()
        last_audit_id = int(state.get(key, 0))

        connection = oracledb.connect(
            user=self.oracle_config.username,
            password=self.oracle_config.password,
            dsn=self.oracle_config.dsn,
        )

        try:
            cursor = connection.cursor()
            try:
                rows = self._fetch_rows(cursor, last_audit_id)
            except Exception as exc:
                message = str(exc)
                if "ORA-00942" in message:
                    self.logger.warning(
                        "Audit export skipped: table not found (%s).", self.table_name
                    )
                    return AuditExportResult(exported_count=0, added_files=[], modified_files=[])
                self.logger.warning("Audit export skipped: %s", exc)
                return AuditExportResult(exported_count=0, added_files=[], modified_files=[])
            if not rows:
                return AuditExportResult(exported_count=0, added_files=[], modified_files=[])

            service_folder = self._safe_name(self.service_name)
            added_files: set[Path] = set()
            modified_files: set[Path] = set()
            max_audit_id = last_audit_id

            for row in rows:
                (
                    audit_id,
                    event_time,
                    sysevent,
                    db_user,
                    login_user,
                    current_schema,
                    os_user,
                    host,
                    ip_address,
                    module,
                    obj_owner,
                    obj_type,
                    obj_name,
                    sql_text,
                ) = row

                audit_id_int = int(audit_id)
                max_audit_id = max(max_audit_id, audit_id_int)

                owner_folder = self._safe_name(str(obj_owner or "UNKNOWN"))
                type_folder = self._safe_name(str(obj_type or "UNKNOWN").upper().replace(" ", "_"))
                object_file = self._safe_name(str(obj_name or f"EVENT_{audit_id_int}"))

                target = self.audit_root / service_folder / owner_folder / type_folder / f"{object_file}.jsonl"
                existed_before = target.exists()

                record = {
                    "audit_id": audit_id_int,
                    "event_time": self._serialize(event_time),
                    "sysevent": self._serialize(sysevent),
                    "db_user": self._serialize(db_user),
                    "login_user": self._serialize(login_user),
                    "current_schema": self._serialize(current_schema),
                    "os_user": self._serialize(os_user),
                    "host": self._serialize(host),
                    "ip_address": self._serialize(ip_address),
                    "module": self._serialize(module),
                    "obj_owner": self._serialize(obj_owner),
                    "obj_type": self._serialize(obj_type),
                    "obj_name": self._serialize(obj_name),
                    "sql_text": self._serialize(sql_text),
                }

                if target in added_files:
                    # 같은 실행에서 신규 파일로 판정된 경우 상태는 added로 유지.
                    pass
                elif existed_before:
                    modified_files.add(target)
                else:
                    added_files.add(target)

                if dry_run:
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False))
                    handle.write("\n")

            if not dry_run:
                state[key] = max_audit_id
                self._save_state(state)

            return AuditExportResult(
                exported_count=len(rows),
                added_files=sorted(added_files, key=lambda path: path.as_posix()),
                modified_files=sorted(modified_files, key=lambda path: path.as_posix()),
            )
        finally:
            connection.close()
