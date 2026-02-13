from __future__ import annotations

import re


TABLESPACE_PATTERN = re.compile(r"(?is)\s+TABLESPACE\s+(?:\"[^\"]+\"|[A-Z0-9_$#]+)")
STORAGE_PATTERN = re.compile(r"(?is)\s+STORAGE\s*\((?:[^)(]+|\([^)(]*\))*\)")


def _is_partition_instance_line(stripped_upper: str) -> bool:
    if stripped_upper.startswith("PARTITION BY"):
        return False
    if stripped_upper.startswith("SUBPARTITION BY"):
        return False
    return stripped_upper.startswith("PARTITION ") or stripped_upper.startswith("SUBPARTITION ")


def _remove_partition_instance_lines(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    skipping = False
    depth = 0

    for line in lines:
        stripped_upper = line.lstrip().upper()
        if not skipping and _is_partition_instance_line(stripped_upper):
            skipping = True
            depth = line.count("(") - line.count(")")
            if depth <= 0 and not line.rstrip().endswith(","):
                skipping = False
                depth = 0
            continue

        if skipping:
            depth += line.count("(") - line.count(")")
            if depth <= 0 and not line.rstrip().endswith(","):
                skipping = False
                depth = 0
            continue

        output.append(line)

    return "\n".join(output)


class DdlNormalizer:
    def __init__(self, line_ending: str = "LF") -> None:
        normalized = line_ending.upper()
        if normalized not in {"LF", "CRLF"}:
            raise ValueError("line_ending must be LF or CRLF.")
        self.line_ending = normalized

    def normalize(self, ddl: str) -> str:
        text = ddl.replace("\r\n", "\n").replace("\r", "\n")
        text = STORAGE_PATTERN.sub("", text)
        text = TABLESPACE_PATTERN.sub("", text)
        text = _remove_partition_instance_lines(text)

        lines = [line.rstrip() for line in text.split("\n")]
        compacted: list[str] = []
        previous_blank = False
        for line in lines:
            is_blank = len(line.strip()) == 0
            if is_blank and previous_blank:
                continue
            compacted.append(line)
            previous_blank = is_blank

        result = "\n".join(compacted).strip()
        if result and not result.endswith("\n"):
            result += "\n"

        if self.line_ending == "CRLF":
            result = result.replace("\n", "\r\n")
        return result

