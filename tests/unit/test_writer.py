from __future__ import annotations

from pathlib import Path

from orasnap.models import DbObject, SnapshotEntry
from orasnap.store.writer import SnapshotWriter


def _entry(name: str, ddl: str) -> SnapshotEntry:
    return SnapshotEntry(
        db_object=DbObject(owner="HMES", object_type="TABLE", object_name=name),
        ddl=ddl,
    )


def test_writer_add_modify_unchanged_delete(tmp_path: Path) -> None:
    writer = SnapshotWriter(snapshot_root=tmp_path / "snapshots")

    first = writer.write([_entry("T1", "CREATE TABLE T1 (ID NUMBER);")])
    assert len(first.added_files) == 1
    assert len(first.modified_files) == 0
    assert len(first.deleted_files) == 0
    assert first.unchanged_files == 0

    target = first.added_files[0]
    assert target.exists()
    assert target.read_text(encoding="utf-8").endswith("\n")

    second = writer.write([_entry("T1", "CREATE TABLE T1 (ID NUMBER);")])
    assert second.unchanged_files == 1
    assert len(second.written_files) == 0

    third = writer.write([_entry("T1", "CREATE TABLE T1 (ID NUMBER, NM VARCHAR2(10));")])
    assert len(third.modified_files) == 1
    assert third.unchanged_files == 0

    fourth = writer.write([])
    assert len(fourth.deleted_files) == 1
    assert not target.exists()


def test_writer_dry_run_does_not_write(tmp_path: Path) -> None:
    writer = SnapshotWriter(snapshot_root=tmp_path / "snapshots")
    result = writer.write([_entry("T2", "CREATE TABLE T2 (ID NUMBER);")], dry_run=True)

    assert len(result.added_files) == 1
    assert not result.added_files[0].exists()

