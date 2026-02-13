from __future__ import annotations

import re
import tempfile
from pathlib import Path

from orasnap.models import SnapshotEntry, WriteResult

SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_name(value: str) -> str:
    cleaned = SAFE_NAME_PATTERN.sub("_", value.strip())
    return cleaned.strip("_") or "unnamed"


class SnapshotWriter:
    def __init__(self, snapshot_root: Path) -> None:
        self.snapshot_root = snapshot_root

    def _entry_path(self, entry: SnapshotEntry) -> Path:
        owner = _safe_name(entry.db_object.owner)
        object_type = _safe_name(entry.db_object.object_type.upper().replace(" ", "_"))
        object_name = _safe_name(entry.db_object.object_name)
        return self.snapshot_root / owner / object_type / f"{object_name}.sql"

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        temp_path.replace(path)

    def write(self, entries: list[SnapshotEntry], dry_run: bool = False) -> WriteResult:
        desired_rel_paths: set[Path] = set()
        added_files: list[Path] = []
        modified_files: list[Path] = []
        unchanged_files = 0

        if not dry_run:
            self.snapshot_root.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            target = self._entry_path(entry)
            rel_path = target.relative_to(self.snapshot_root)
            desired_rel_paths.add(rel_path)

            content = entry.ddl
            if not content.endswith("\n"):
                content += "\n"

            exists_before = target.exists()
            if exists_before:
                current = target.read_text(encoding="utf-8")
                if current == content:
                    unchanged_files += 1
                    continue

            if exists_before:
                modified_files.append(target)
            else:
                added_files.append(target)

            if dry_run:
                continue
            self._atomic_write(target, content)

        deleted_files: list[Path] = []
        if self.snapshot_root.exists():
            for existing in self.snapshot_root.rglob("*.sql"):
                rel_path = existing.relative_to(self.snapshot_root)
                if rel_path in desired_rel_paths:
                    continue
                deleted_files.append(existing)
                if dry_run:
                    continue
                existing.unlink()

        return WriteResult(
            added_files=added_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            unchanged_files=unchanged_files,
        )

