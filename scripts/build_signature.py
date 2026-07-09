"""Derive a stable, branch-name-safe signature for a Slack-reported error."""
from __future__ import annotations

import hashlib
import re


def build_signature(exception_type: str, frames: list[str]) -> str:
    """frames: 1-2 'file:line' strings, top stack frame first."""
    normalized = exception_type.strip() + "|" + "|".join(f.strip() for f in frames)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

    slug_source = exception_type.strip().split(":")[-1]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug_source).strip("-").lower()[:30]

    return f"{slug}-{digest}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: build_signature.py <exception_type> <frame1> [frame2]", file=sys.stderr)
        sys.exit(1)

    exception_type = sys.argv[1]
    frames = sys.argv[2:4]
    print(build_signature(exception_type, frames))
