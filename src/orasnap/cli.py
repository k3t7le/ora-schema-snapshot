from __future__ import annotations

import argparse
import sys

from orasnap.pipeline import run_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orasnap",
        description="Oracle schema snapshot tool (snapshot only, no migration).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Extract, normalize, write snapshots, and optionally commit/push.",
    )
    snapshot_parser.add_argument(
        "--config",
        default="config/snapshot.yml",
        help="Path to YAML config file.",
    )

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Run extraction and normalization without writing files or git updates.",
    )
    dry_run_parser.add_argument(
        "--config",
        default="config/snapshot.yml",
        help="Path to YAML config file.",
    )

    return parser


def _print_summary(result) -> None:
    print(f"extracted={result.extracted_count}")
    print(f"failed={result.failed_count}")
    print(f"written={result.written_count}")
    print(f"deleted={result.deleted_count}")
    print(f"unchanged={result.unchanged_count}")
    print(f"committed={result.committed}")
    print(f"pushed={result.pushed}")
    if result.log_file:
        print(f"log_file={result.log_file}")
    if result.commit_sha:
        print(f"commit_sha={result.commit_sha}")
    if result.failures:
        print("failures:")
        for failure in result.failures:
            print(f"  - {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    dry_run = args.command == "dry-run"
    try:
        result = run_snapshot(args.config, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover - CLI integration path.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

