"""Read/write per-target Slack cursor state (state/cursors.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def load_cursors(path: "str | Path") -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def get_cursor(cursors: dict[str, str], target_name: str) -> Optional[str]:
    return cursors.get(target_name)


def set_cursor(cursors: dict[str, str], target_name: str, timestamp: str) -> dict[str, str]:
    updated = dict(cursors)
    updated[target_name] = timestamp
    return updated


def save_cursors(path: "str | Path", cursors: dict[str, str]) -> None:
    Path(path).write_text(json.dumps(cursors, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("usage: cursor_store.py <get|set> <path> <target_name> [timestamp]", file=sys.stderr)
        sys.exit(1)

    action, path, target_name = sys.argv[1], sys.argv[2], sys.argv[3]
    cursors = load_cursors(path)

    if action == "get":
        value = get_cursor(cursors, target_name)
        print(value if value is not None else "")
    elif action == "set":
        timestamp = sys.argv[4]
        cursors = set_cursor(cursors, target_name, timestamp)
        save_cursors(path, cursors)
        print(f"set {target_name} -> {timestamp}")
    else:
        print(f"unknown action '{action}'", file=sys.stderr)
        sys.exit(1)
