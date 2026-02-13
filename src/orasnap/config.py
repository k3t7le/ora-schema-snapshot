from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_OBJECT_TYPES = [
    "TABLE",
    "VIEW",
    "INDEX",
    "SEQUENCE",
    "SYNONYM",
    "TRIGGER",
    "TYPE",
    "TYPE BODY",
    "PROCEDURE",
    "FUNCTION",
    "PACKAGE",
    "PACKAGE BODY",
    "MATERIALIZED VIEW",
]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class OracleConfig:
    host: str
    port: int
    service_name: str
    username: str
    password: str

    @property
    def dsn(self) -> str:
        return f"{self.host}:{self.port}/{self.service_name}"


@dataclass(frozen=True)
class ScopeConfig:
    discovery_mode: str = "hybrid"
    include_schemas: list[str] = field(default_factory=list)
    exclude_schemas: list[str] = field(default_factory=list)
    object_types: list[str] = field(default_factory=lambda: list(DEFAULT_OBJECT_TYPES))


@dataclass(frozen=True)
class OutputConfig:
    snapshot_root: Path
    line_ending: str = "LF"


@dataclass(frozen=True)
class GitConfig:
    repo_path: Path
    branch: str | None = None
    commit_message_template: str = "snapshot: {timestamp}"
    auto_push: bool = True
    remote: str = "origin"


@dataclass(frozen=True)
class LogsConfig:
    retention_days: int = 30


@dataclass(frozen=True)
class AppConfig:
    oracle: OracleConfig
    scope: ScopeConfig
    output: OutputConfig
    git: GitConfig
    logs: LogsConfig


def _to_upper_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("List type is required.")
    return [str(item).strip().upper() for item in raw if str(item).strip()]


def _resolve_path(raw: str | Path, base_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Root config must be a map/dictionary.")

    oracle_raw = raw.get("oracle") or {}
    scope_raw = raw.get("scope") or {}
    output_raw = raw.get("output") or {}
    git_raw = raw.get("git") or {}
    logs_raw = raw.get("logs") or {}

    try:
        oracle = OracleConfig(
            host=str(oracle_raw["host"]).strip(),
            port=int(oracle_raw.get("port", 1521)),
            service_name=str(oracle_raw["service_name"]).strip(),
            username=str(oracle_raw["username"]).strip(),
            password=str(oracle_raw["password"]),
        )
    except KeyError as exc:
        raise ConfigError(f"Missing oracle config field: {exc}") from exc

    if not oracle.host or not oracle.service_name or not oracle.username:
        raise ConfigError("oracle.host/service_name/username must be non-empty.")

    discovery_mode = str(scope_raw.get("discovery_mode", "hybrid")).strip().lower()
    if discovery_mode not in {"hybrid"}:
        raise ConfigError("scope.discovery_mode must be 'hybrid'.")

    include_schemas = _to_upper_list(scope_raw.get("include_schemas"))
    exclude_schemas = _to_upper_list(scope_raw.get("exclude_schemas"))
    object_types = _to_upper_list(scope_raw.get("object_types")) or list(DEFAULT_OBJECT_TYPES)

    scope = ScopeConfig(
        discovery_mode=discovery_mode,
        include_schemas=include_schemas,
        exclude_schemas=exclude_schemas,
        object_types=object_types,
    )

    base_dir = path.parent
    line_ending = str(output_raw.get("line_ending", "LF")).strip().upper()
    if line_ending not in {"LF", "CRLF"}:
        raise ConfigError("output.line_ending must be LF or CRLF.")

    snapshot_root = _resolve_path(output_raw.get("snapshot_root", "snapshots"), base_dir)
    output = OutputConfig(snapshot_root=snapshot_root, line_ending=line_ending)

    repo_path = _resolve_path(git_raw.get("repo_path", "."), base_dir)
    git = GitConfig(
        repo_path=repo_path,
        branch=(str(git_raw["branch"]).strip() if "branch" in git_raw and git_raw["branch"] else None),
        commit_message_template=str(git_raw.get("commit_message_template", "snapshot: {timestamp}")),
        auto_push=bool(git_raw.get("auto_push", True)),
        remote=str(git_raw.get("remote", "origin")).strip() or "origin",
    )

    retention_days = int(logs_raw.get("retention_days", 30))
    if retention_days < 1:
        raise ConfigError("logs.retention_days must be >= 1.")
    logs = LogsConfig(retention_days=retention_days)

    return AppConfig(oracle=oracle, scope=scope, output=output, git=git, logs=logs)

