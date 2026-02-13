from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbObject:
    owner: str
    object_type: str
    object_name: str


@dataclass(frozen=True)
class ExtractedDdl:
    db_object: DbObject
    ddl: str


@dataclass(frozen=True)
class SnapshotEntry:
    db_object: DbObject
    ddl: str


@dataclass(frozen=True)
class WriteResult:
    added_files: list[Path]
    modified_files: list[Path]
    deleted_files: list[Path]
    unchanged_files: int

    @property
    def written_files(self) -> list[Path]:
        return [*self.added_files, *self.modified_files]


@dataclass(frozen=True)
class GitResult:
    committed: bool
    commit_sha: str | None
    pushed: bool

