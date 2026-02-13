from __future__ import annotations

import subprocess
from pathlib import Path

from orasnap.vcs.git_ops import GitOps


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    init = _run(["git", "init"], cwd=repo)
    assert init.returncode == 0, init.stderr
    assert _run(["git", "config", "user.email", "orasnap@example.com"], cwd=repo).returncode == 0
    assert _run(["git", "config", "user.name", "orasnap"], cwd=repo).returncode == 0

    # Ensure branch exists for verify_branch/current_branch.
    seed = repo / ".seed"
    seed.write_text("seed\n", encoding="utf-8")
    assert _run(["git", "add", "--", ".seed"], cwd=repo).returncode == 0
    assert _run(["git", "commit", "-m", "seed"], cwd=repo).returncode == 0


def test_git_ops_commit_if_changed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    snapshots = repo / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    (snapshots / "a.sql").write_text("A\n", encoding="utf-8")

    git_ops = GitOps(repo_path=repo)
    first = git_ops.commit_if_changed(
        paths=[snapshots],
        message="snapshot 1",
        auto_push=False,
        branch=None,
    )
    assert first.committed is True
    assert first.commit_sha
    assert first.pushed is False

    second = git_ops.commit_if_changed(
        paths=[snapshots],
        message="snapshot 2",
        auto_push=False,
        branch=None,
    )
    assert second.committed is False
    assert second.commit_sha is None
    assert second.pushed is False

