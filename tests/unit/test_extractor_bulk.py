from __future__ import annotations

from orasnap.config import OracleConfig, ScopeConfig
from orasnap.models import DbObject
from orasnap.oracle.extractor import OracleMetadataExtractor


class _FakeLob:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def read(self) -> str:
        return self.payload


class _FakeCursor:
    def __init__(self, behaviors: dict[tuple[object, ...], object]) -> None:
        self.behaviors = behaviors
        self._rows: list[tuple[object, ...]] = []

    def execute(self, _sql: str, binds: list[object]) -> None:
        key = tuple(binds)
        behavior = self.behaviors[key]
        if isinstance(behavior, Exception):
            raise behavior
        self._rows = behavior

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


def _build_extractor() -> OracleMetadataExtractor:
    return OracleMetadataExtractor(
        oracle_config=OracleConfig(
            host="127.0.0.1",
            port=1521,
            service_name="ORCLPDB",
            username="ORASNAP_SVC",
            password="pw",
        ),
        scope_config=ScopeConfig(
            discovery_mode="hybrid",
            include_schemas=["HMES"],
            exclude_schemas=[],
            object_types=["VIEW", "SEQUENCE", "PACKAGE BODY"],
        ),
    )


def test_extract_ddl_bulk_success() -> None:
    extractor = _build_extractor()
    cursor = _FakeCursor(
        {
            ("VIEW", "HMES", "HMES", "VIEW", "V_A", "V_B"): [
                ("V_A", "DDL_VIEW_A"),
                ("V_B", _FakeLob("DDL_VIEW_B")),
            ],
            ("PACKAGE_BODY", "HMES", "HMES", "PACKAGE BODY", "PKG_UTIL"): [
                ("PKG_UTIL", "DDL_PKG_BODY")
            ],
        }
    )

    objects = [
        DbObject(owner="HMES", object_type="VIEW", object_name="V_A"),
        DbObject(owner="HMES", object_type="VIEW", object_name="V_B"),
        DbObject(owner="HMES", object_type="PACKAGE BODY", object_name="PKG_UTIL"),
    ]
    ddls, failed = extractor._extract_ddl_bulk(cursor, objects)

    assert failed == []
    assert ddls[("HMES", "VIEW", "V_A")] == "DDL_VIEW_A"
    assert ddls[("HMES", "VIEW", "V_B")] == "DDL_VIEW_B"
    assert ddls[("HMES", "PACKAGE BODY", "PKG_UTIL")] == "DDL_PKG_BODY"


def test_extract_ddl_bulk_group_failure_marks_fallback_targets() -> None:
    extractor = _build_extractor()
    cursor = _FakeCursor(
        {
            ("VIEW", "HMES", "HMES", "VIEW", "V_A", "V_B"): RuntimeError("bulk failed"),
            ("SEQUENCE", "HMES", "HMES", "SEQUENCE", "SEQ_A"): [("SEQ_A", "DDL_SEQ_A")],
        }
    )

    view_a = DbObject(owner="HMES", object_type="VIEW", object_name="V_A")
    view_b = DbObject(owner="HMES", object_type="VIEW", object_name="V_B")
    seq_a = DbObject(owner="HMES", object_type="SEQUENCE", object_name="SEQ_A")

    ddls, failed = extractor._extract_ddl_bulk(cursor, [view_a, view_b, seq_a])

    assert ddls == {("HMES", "SEQUENCE", "SEQ_A"): "DDL_SEQ_A"}
    assert failed == [view_a, view_b]


def test_extract_ddl_bulk_missing_rows_mark_fallback_targets() -> None:
    extractor = _build_extractor()
    cursor = _FakeCursor(
        {
            ("VIEW", "HMES", "HMES", "VIEW", "V_A", "V_B"): [("V_A", "DDL_VIEW_A")],
        }
    )

    view_a = DbObject(owner="HMES", object_type="VIEW", object_name="V_A")
    view_b = DbObject(owner="HMES", object_type="VIEW", object_name="V_B")

    ddls, failed = extractor._extract_ddl_bulk(cursor, [view_a, view_b])

    assert ddls == {("HMES", "VIEW", "V_A"): "DDL_VIEW_A"}
    assert failed == [view_b]
