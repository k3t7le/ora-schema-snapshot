from __future__ import annotations

from pathlib import Path

from orasnap.pipeline import MAX_COMMIT_MESSAGE_FILES, _build_commit_message


def test_commit_message_includes_change_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    added = [repo / "a.sql"]
    modified = [repo / "b.sql"]
    deleted = [repo / "c.sql"]

    message = _build_commit_message(
        template="snapshot: {timestamp}",
        repo_path=repo,
        added_files=added,
        modified_files=modified,
        deleted_files=deleted,
    )

    assert "Changed files:" in message
    assert "- A a.sql" in message
    assert "- M b.sql" in message
    assert "- D c.sql" in message


def test_commit_message_fallback_for_bad_template(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    message = _build_commit_message(
        template="snapshot: {bad_key}",
        repo_path=repo,
        added_files=[],
        modified_files=[],
        deleted_files=[],
    )
    assert message.startswith("snapshot: ")


def test_commit_message_limits_file_list(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    added = [repo / f"{index}.sql" for index in range(MAX_COMMIT_MESSAGE_FILES + 2)]

    message = _build_commit_message(
        template="snapshot: {timestamp}",
        repo_path=repo,
        added_files=added,
        modified_files=[],
        deleted_files=[],
    )

    assert f"(+2 more)" in message

