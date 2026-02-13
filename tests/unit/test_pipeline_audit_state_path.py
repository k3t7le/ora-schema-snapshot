from __future__ import annotations

import logging
from pathlib import Path

import orasnap.pipeline as pipeline_module
from orasnap.config import AppConfig, AuditConfig, GitConfig, LogsConfig, OracleConfig, OutputConfig, ScopeConfig
from orasnap.pipeline import SnapshotRunResult


def _build_config(tmp_path: Path, state_file: str) -> AppConfig:
    return AppConfig(
        oracle=OracleConfig(
            host="127.0.0.1",
            port=1521,
            service_name="ORCLPDB",
            username="ORASNAP_SVC",
            password="pw",
        ),
        scope=ScopeConfig(
            discovery_mode="hybrid",
            include_schemas=["HMES"],
            exclude_schemas=["SYS"],
            object_types=["TABLE"],
        ),
        output=OutputConfig(snapshot_root=tmp_path / "snapshots", line_ending="LF"),
        git=GitConfig(repo_path=tmp_path / "repo", auto_push=False),
        logs=LogsConfig(retention_days=30),
        audit=AuditConfig(enabled=True, root=None, table="DDL_AUDIT_LOG", state_file=state_file),
    )


def test_run_snapshot_uses_project_root_for_relative_audit_state(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config" / "snapshot.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("dummy: true\n", encoding="utf-8")

    config = _build_config(tmp_path, ".orasnap_audit_state.json")
    monkeypatch.setattr(pipeline_module, "load_config", lambda _: config)
    monkeypatch.setattr(pipeline_module, "_setup_logger", lambda _: logging.getLogger("test"))
    monkeypatch.setattr(pipeline_module, "_purge_old_logs", lambda *_: 0)

    captured: dict[str, Path] = {}

    class _FakePipeline:
        def __init__(self, *, config, logger, log_file, audit_state_path) -> None:
            captured["audit_state_path"] = audit_state_path

        def run(self, *, dry_run: bool) -> SnapshotRunResult:
            return SnapshotRunResult(
                extracted_count=0,
                failed_count=0,
                written_count=0,
                deleted_count=0,
                unchanged_count=0,
                audit_exported_count=0,
                committed=False,
                commit_sha=None,
                pushed=False,
                failures=[],
                log_file=None,
            )

    monkeypatch.setattr(pipeline_module, "SnapshotPipeline", _FakePipeline)

    pipeline_module.run_snapshot(config_file, dry_run=True)
    assert captured["audit_state_path"] == (tmp_path / ".orasnap_audit_state.json")


def test_run_snapshot_uses_absolute_audit_state_as_is(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "config" / "snapshot.yml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("dummy: true\n", encoding="utf-8")

    absolute_state_path = tmp_path / "state" / "audit_state.json"
    config = _build_config(tmp_path, str(absolute_state_path))
    monkeypatch.setattr(pipeline_module, "load_config", lambda _: config)
    monkeypatch.setattr(pipeline_module, "_setup_logger", lambda _: logging.getLogger("test"))
    monkeypatch.setattr(pipeline_module, "_purge_old_logs", lambda *_: 0)

    captured: dict[str, Path] = {}

    class _FakePipeline:
        def __init__(self, *, config, logger, log_file, audit_state_path) -> None:
            captured["audit_state_path"] = audit_state_path

        def run(self, *, dry_run: bool) -> SnapshotRunResult:
            return SnapshotRunResult(
                extracted_count=0,
                failed_count=0,
                written_count=0,
                deleted_count=0,
                unchanged_count=0,
                audit_exported_count=0,
                committed=False,
                commit_sha=None,
                pushed=False,
                failures=[],
                log_file=None,
            )

    monkeypatch.setattr(pipeline_module, "SnapshotPipeline", _FakePipeline)

    pipeline_module.run_snapshot(config_file, dry_run=True)
    assert captured["audit_state_path"] == absolute_state_path

