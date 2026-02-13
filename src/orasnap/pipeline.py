from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from orasnap.config import AppConfig, load_config
from orasnap.models import SnapshotEntry
from orasnap.normalize.ddl_normalizer import DdlNormalizer
from orasnap.oracle.audit_exporter import AuditExportResult, OracleAuditExporter
from orasnap.oracle.extractor import OracleMetadataExtractor
from orasnap.store.writer import SnapshotWriter
from orasnap.vcs.git_ops import GitOps


@dataclass(frozen=True)
class SnapshotRunResult:
    extracted_count: int
    failed_count: int
    written_count: int
    deleted_count: int
    unchanged_count: int
    audit_exported_count: int
    committed: bool
    commit_sha: str | None
    pushed: bool
    failures: list[str]
    log_file: Path | None


MAX_COMMIT_MESSAGE_FILES = 30


def _to_repo_relative_path(path: Path, repo_path: Path) -> str:
    resolved_path = path.resolve()
    resolved_repo = repo_path.resolve()
    try:
        return resolved_path.relative_to(resolved_repo).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _build_commit_message(
    template: str,
    repo_path: Path,
    added_files: list[Path],
    modified_files: list[Path],
    deleted_files: list[Path],
) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        base = template.format(timestamp=timestamp)
    except KeyError:
        base = f"snapshot: {timestamp}"

    changed_lines: list[str] = []
    for path in added_files:
        changed_lines.append(f"A {_to_repo_relative_path(path, repo_path)}")
    for path in modified_files:
        changed_lines.append(f"M {_to_repo_relative_path(path, repo_path)}")
    for path in deleted_files:
        changed_lines.append(f"D {_to_repo_relative_path(path, repo_path)}")

    if not changed_lines:
        return base

    subject = f"{base} ({len(changed_lines)} files)"
    body = ["", "Changed files:"]
    for line in changed_lines[:MAX_COMMIT_MESSAGE_FILES]:
        body.append(f"- {line}")
    remaining = len(changed_lines) - MAX_COMMIT_MESSAGE_FILES
    if remaining > 0:
        body.append(f"- ... (+{remaining} more)")
    return subject + "\n" + "\n".join(body)


def _resolve_logs_dir(config_path: Path) -> Path:
    config_path = config_path.resolve()
    config_parent = config_path.parent
    if config_parent.name.lower() == "config":
        return config_parent.parent / "logs"
    return config_parent / "logs"


def _resolve_project_root(config_path: Path) -> Path:
    config_path = config_path.resolve()
    config_parent = config_path.parent
    if config_parent.name.lower() == "config":
        return config_parent.parent
    return config_parent


def _resolve_audit_root(config: AppConfig) -> Path:
    if config.audit.root is not None:
        return config.audit.root
    return config.git.repo_path / "_audit"


def _setup_logger(log_file_path: Path) -> logging.Logger:
    logger = logging.getLogger("orasnap")

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def _purge_old_logs(logs_dir: Path, retention_days: int, logger: logging.Logger) -> int:
    if retention_days < 1 or not logs_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for log_file in logs_dir.glob("orasnap-*.log"):
        try:
            modified_at = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)
            if modified_at < cutoff:
                log_file.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Failed to delete old log file: %s (%s)", log_file, exc)

    return removed


class SnapshotPipeline:
    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger | None = None,
        log_file: Path | None = None,
        audit_state_path: Path | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("orasnap")
        self.log_file = log_file
        self.audit_state_path = audit_state_path

    def run(self, dry_run: bool) -> SnapshotRunResult:
        self.logger.info("Snapshot run started. dry_run=%s", dry_run)

        extraction_started = perf_counter()
        extractor = OracleMetadataExtractor(
            oracle_config=self.config.oracle,
            scope_config=self.config.scope,
            logger=self.logger,
        )
        extraction = extractor.extract()
        extraction_elapsed = perf_counter() - extraction_started
        self.logger.info(
            "Extraction stage finished in %.2fs. extracted=%s failed=%s",
            extraction_elapsed,
            len(extraction.items),
            len(extraction.failures),
        )
        normalizer = DdlNormalizer(line_ending=self.config.output.line_ending)

        write_started = perf_counter()
        entries: list[SnapshotEntry] = []
        for item in extraction.items:
            normalized = normalizer.normalize(item.ddl)
            entries.append(SnapshotEntry(db_object=item.db_object, ddl=normalized))

        writer = SnapshotWriter(snapshot_root=self.config.output.snapshot_root)
        write_result = writer.write(entries, dry_run=dry_run)
        write_elapsed = perf_counter() - write_started
        self.logger.info(
            "Write stage finished in %.2fs. written=%s deleted=%s unchanged=%s",
            write_elapsed,
            len(write_result.written_files),
            len(write_result.deleted_files),
            write_result.unchanged_files,
        )

        audit_result = AuditExportResult(exported_count=0, added_files=[], modified_files=[])
        audit_root = _resolve_audit_root(self.config)
        if self.config.audit.enabled and not dry_run:
            audit_started = perf_counter()
            audit_exporter = OracleAuditExporter(
                oracle_config=self.config.oracle,
                service_name=self.config.oracle.service_name,
                audit_root=audit_root,
                state_path=self.audit_state_path or Path("logs/audit_state.json"),
                table_name=self.config.audit.table,
                logger=self.logger,
            )
            audit_result = audit_exporter.export(dry_run=False)
            audit_elapsed = perf_counter() - audit_started
            if audit_result.exported_count:
                self.logger.info(
                    "Audit export finished in %.2fs. exported=%s added=%s modified=%s root=%s",
                    audit_elapsed,
                    audit_result.exported_count,
                    len(audit_result.added_files),
                    len(audit_result.modified_files),
                    audit_root,
                )
            else:
                self.logger.info("Audit export finished in %.2fs. exported=0", audit_elapsed)

        all_added_files = [*write_result.added_files, *audit_result.added_files]
        all_modified_files = [*write_result.modified_files, *audit_result.modified_files]

        committed = False
        commit_sha = None
        pushed = False
        if not dry_run:
            git_started = perf_counter()
            git_ops = GitOps(repo_path=self.config.git.repo_path)
            commit_message = _build_commit_message(
                template=self.config.git.commit_message_template,
                repo_path=self.config.git.repo_path,
                added_files=all_added_files,
                modified_files=all_modified_files,
                deleted_files=write_result.deleted_files,
            )
            stage_paths = [self.config.output.snapshot_root]
            if self.config.audit.enabled and audit_root.exists():
                stage_paths.append(audit_root)
            git_result = git_ops.commit_if_changed(
                paths=stage_paths,
                message=commit_message,
                auto_push=self.config.git.auto_push,
                branch=self.config.git.branch,
                remote=self.config.git.remote,
            )
            committed = git_result.committed
            commit_sha = git_result.commit_sha
            pushed = git_result.pushed
            git_elapsed = perf_counter() - git_started
            self.logger.info(
                "Git stage finished in %.2fs. committed=%s pushed=%s",
                git_elapsed,
                committed,
                pushed,
            )

        self.logger.info(
            "Snapshot run finished. extracted=%s failed=%s written=%s deleted=%s unchanged=%s audit_exported=%s committed=%s pushed=%s",
            len(extraction.items),
            len(extraction.failures),
            len(write_result.written_files),
            len(write_result.deleted_files),
            write_result.unchanged_files,
            audit_result.exported_count,
            committed,
            pushed,
        )

        return SnapshotRunResult(
            extracted_count=len(extraction.items),
            failed_count=len(extraction.failures),
            written_count=len(write_result.written_files),
            deleted_count=len(write_result.deleted_files),
            unchanged_count=write_result.unchanged_files,
            audit_exported_count=audit_result.exported_count,
            committed=committed,
            commit_sha=commit_sha,
            pushed=pushed,
            failures=extraction.failures,
            log_file=self.log_file,
        )


def run_snapshot(config_path: str | Path, dry_run: bool = False) -> SnapshotRunResult:
    config_file = Path(config_path).resolve()
    config = load_config(config_file)
    project_root = _resolve_project_root(config_file)
    logs_dir = _resolve_logs_dir(config_file)
    local_date = datetime.now().strftime("%Y%m%d")
    log_file = logs_dir / f"orasnap-{local_date}.log"
    logger = _setup_logger(log_file)
    removed_logs = _purge_old_logs(logs_dir, config.logs.retention_days, logger)
    if removed_logs:
        logger.info(
            "Log retention applied. removed=%s retention_days=%s",
            removed_logs,
            config.logs.retention_days,
        )

    configured_state_path = Path(config.audit.state_file)
    if configured_state_path.is_absolute():
        audit_state_path = configured_state_path
    else:
        audit_state_path = project_root / configured_state_path
    pipeline = SnapshotPipeline(
        config=config,
        logger=logger,
        log_file=log_file,
        audit_state_path=audit_state_path,
    )
    return pipeline.run(dry_run=dry_run)
