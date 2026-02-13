from __future__ import annotations

import subprocess
from pathlib import Path

from orasnap.models import GitResult


class GitError(RuntimeError):
    pass


class GitOps:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        process = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if check and process.returncode != 0:
            raise GitError(process.stderr.strip() or process.stdout.strip())
        return process

    def ensure_repo(self) -> None:
        process = self._run("rev-parse", "--is-inside-work-tree", check=False)
        if process.returncode != 0 or process.stdout.strip().lower() != "true":
            raise GitError(f"Not a git repository: {self.repo_path}")

    def current_branch(self) -> str:
        result = self._run("rev-parse", "--abbrev-ref", "HEAD", check=False)
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch:
                return branch

        fallback = self._run("symbolic-ref", "--short", "HEAD", check=False)
        if fallback.returncode == 0 and fallback.stdout.strip():
            return fallback.stdout.strip()

        raise GitError(
            result.stderr.strip()
            or fallback.stderr.strip()
            or "Unable to detect current branch."
        )

    def verify_branch(self, expected_branch: str | None) -> str:
        current = self.current_branch()
        if expected_branch and current != expected_branch:
            raise GitError(f"Current branch is '{current}', expected '{expected_branch}'.")
        return current

    def stage(self, paths: list[Path]) -> None:
        if not paths:
            return
        normalized: list[str] = []
        repo_resolved = self.repo_path.resolve()
        for path in paths:
            resolved = path.resolve()
            try:
                normalized.append(str(resolved.relative_to(repo_resolved)))
            except ValueError:
                normalized.append(str(resolved))
        self._run("add", "--", *normalized)

    def has_cached_diff(self) -> bool:
        process = self._run("status", "--porcelain", "--untracked-files=no", check=False)
        if process.returncode != 0:
            raise GitError(process.stderr.strip() or process.stdout.strip())
        return bool(process.stdout.strip())

    def commit_if_changed(
        self,
        paths: list[Path],
        message: str,
        auto_push: bool,
        branch: str | None,
        remote: str = "origin",
    ) -> GitResult:
        self.ensure_repo()
        current = self.verify_branch(branch)
        self.stage(paths)

        if not self.has_cached_diff():
            return GitResult(committed=False, commit_sha=None, pushed=False)

        self._run("commit", "-m", message)
        sha = self._run("rev-parse", "HEAD").stdout.strip()

        pushed = False
        if auto_push:
            self._run("push", remote, current)
            pushed = True

        return GitResult(committed=True, commit_sha=sha, pushed=pushed)

