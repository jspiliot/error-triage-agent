"""Load and validate targets.yaml for the error triage agent."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = ("name", "slack_channel_id", "repo", "branch")
PLACEHOLDER_CHECK_FIELDS = ("slack_channel_id", "repo")
DEFAULT_MAX_ERRORS_PER_RUN = 5


def load_targets(path: "str | Path") -> list[dict[str, Any]]:
    """Load targets.yaml, validate required fields, apply defaults.

    Raises ValueError if a target is missing a required field, if there
    are no targets, or if a target still has a REPLACE_ME placeholder.
    """
    data = yaml.safe_load(Path(path).read_text())
    targets = (data or {}).get("targets", [])
    if not targets:
        raise ValueError(f"No targets found in {path}")

    loaded = []
    for i, target in enumerate(targets):
        for field in REQUIRED_FIELDS:
            if not target.get(field):
                raise ValueError(f"Target #{i} is missing required field '{field}'")
        for field in PLACEHOLDER_CHECK_FIELDS:
            if "REPLACE_ME" in target[field]:
                raise ValueError(
                    f"Target '{target['name']}' still has a placeholder '{field}' "
                    "- fill in targets.yaml before running"
                )
        merged = dict(target)
        merged.setdefault("max_errors_per_run", DEFAULT_MAX_ERRORS_PER_RUN)
        loaded.append(merged)
    return loaded


if __name__ == "__main__":
    import json
    import sys

    result = load_targets(sys.argv[1] if len(sys.argv) > 1 else "targets.yaml")
    print(json.dumps(result, indent=2))
