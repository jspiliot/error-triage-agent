# Slack Error Triage Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `error-triage-agent` repo: config, state helpers, and the daily-run instructions document (`AGENT.md`) that a Claude Code `/schedule` cloud routine executes once a day to triage errors posted to 4 Slack channels and open PRs with tested fixes.

**Architecture:** A handful of small, independently testable Python scripts (target loading, cursor state, signature hashing) provide deterministic building blocks. `AGENT.md` is a runbook consumed by the scheduled Claude routine at execution time — it is not itself executable code, so its own correctness is validated by a documented dry-run walkthrough rather than pytest.

**Tech Stack:** Python 3 (stdlib + PyYAML) for helper scripts, pytest for their tests, `gh` CLI for GitHub, Slack Web API via `curl`, git worktrees for investigation clones.

## Global Constraints

- Exactly 4 targets, fixed: `backend-server@master`, `backend-server@total-media-master`, `frontend-b2b@master`, `frontend-b2c@main`.
- Default `max_errors_per_run` is 5, overridable per target in `targets.yaml`.
- A channel with no stored cursor yet uses "now" as its starting point — never backfills full history.
- Dedup: `gh search prs --repo <repo> --state open "<signature>"`, plus a branch-name fallback check for `autofix/<signature>`.
- PRs are opened ready-for-review (never draft), with `jspiliot` requested as reviewer, title prefixed `[auto-fix]`.
- No confident fix + tests pass → PR. Otherwise → reply in the original Slack thread with findings. Never open a PR with failing tests.
- No sensitive-area denylist — any part of a target repo is fair game for a fix; PR review is the safety net.
- Self-reporting (daily summary + run-level failure alerts) goes to the `#error-triage-agent` channel, ID supplied via `ERROR_TRIAGE_REPORT_CHANNEL_ID`.
- Schedule cadence: daily, `0 6 * * *` (06:00 UTC).
- A hard failure on one target must never block processing of the other targets.

---

### Task 1: Repo scaffold, dependencies, and README

**Files:**
- Create: `README.md`
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `scripts/__init__.py`
- Create: `state/cursors.json`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: repo skeleton that later tasks add files into; `pytest.ini` makes `scripts/` importable from `tests/` as `scripts.<module>`.

- [ ] **Step 1: Write `requirements.txt`**

```
pyyaml>=6.0
pytest>=7.0
```

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create `scripts/__init__.py`** (empty file, makes `scripts` an importable package)

```python
```

- [ ] **Step 5: Create initial `state/cursors.json`**

```json
{}
```

- [ ] **Step 6: Write `README.md`**

```markdown
# error-triage-agent

Daily Claude Code scheduled routine that reads error logs posted to Slack
for 4 deployment targets, investigates root causes, and opens a PR with a
tested fix when confident — or replies in the Slack thread with its
findings when it isn't.

## Prerequisites

Before the daily schedule can run for real, gather:

- A Slack bot token (`SLACK_BOT_TOKEN`) with `channels:history` and
  `chat:write` scopes, invited into all 5 channels below.
- The 4 target channel IDs (one per row in `targets.yaml`).
- A new `#error-triage-agent` Slack channel, with the bot invited, and its
  channel ID (`ERROR_TRIAGE_REPORT_CHANNEL_ID`).
- Confirmation that the environment running the schedule has `gh` access
  (push + PR create) to `backend-server`, `frontend-b2b`, and
  `frontend-b2c`.

## Setup

1. `pip install -r requirements.txt`
2. Fill in the `REPLACE_ME_*` values in `targets.yaml` with the real Slack
   channel IDs and `org/repo` names.
3. Run `pytest` — all helper-script tests should pass.

## How the daily run works

`AGENT.md` is the runbook a Claude Code `/schedule` routine executes once a
day. See that file for the full step-by-step flow. In short: for each of
the 4 targets, it fetches new Slack messages, skips ones already handled
(via a GitHub PR/branch dedup check), investigates root cause, and either
opens a PR or replies in the Slack thread.

## Dry-run validation

`AGENT.md` supports `DRY_RUN=true` (no pushes/PRs/real Slack replies — logs
intended actions to `#error-triage-agent` instead) and `DRY_RUN_FIXTURE`
(reads messages from a local JSON file instead of the Slack API). See
`tests/fixtures/sample_slack_messages.json` for the fixture format, and the
"Dry-run fixture validation" section of the implementation plan for the
manual walkthrough checklist.

## Repository layout

- `AGENT.md` — the daily-run instructions
- `targets.yaml` — the 4 (Slack channel, repo, branch) mappings
- `state/cursors.json` — last-processed Slack timestamp per target
- `scripts/` — small deterministic helpers used by the daily run
- `tests/` — tests for `scripts/`, plus dry-run fixtures
```

- [ ] **Step 7: Verify README structure**

Run: `grep -c "^## " README.md`
Expected: `5`

- [ ] **Step 8: Commit**

```bash
git add README.md requirements.txt pytest.ini .gitignore scripts/__init__.py state/cursors.json
git commit -m "Scaffold error-triage-agent repo"
```

---

### Task 2: Target loader (`scripts/load_targets.py`)

**Files:**
- Create: `scripts/load_targets.py`
- Create: `targets.yaml`
- Test: `tests/test_load_targets.py`

**Interfaces:**
- Consumes: nothing
- Produces: `load_targets(path: str | Path) -> list[dict]`. Each dict has keys `name`, `slack_channel_id`, `repo`, `branch`, `max_errors_per_run` (int, defaults to 5). Raises `ValueError` if a required field (`name`, `slack_channel_id`, `repo`, `branch`) is missing, if `targets` is empty, or if `slack_channel_id`/`repo` still contains the substring `REPLACE_ME`. CLI: `python3 scripts/load_targets.py [path]` prints the loaded list as JSON.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_load_targets.py
import pytest

from scripts.load_targets import load_targets

VALID_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    repo: adadot/frontend-b2c
    branch: main
"""

VALID_YAML_WITH_CAP = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    repo: adadot/frontend-b2c
    branch: main
    max_errors_per_run: 2
"""

MISSING_FIELD_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: C123
    branch: main
"""

PLACEHOLDER_YAML = """
targets:
  - name: frontend-b2c
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: adadot/frontend-b2c
    branch: main
"""

EMPTY_YAML = "targets: []\n"


def _write(tmp_path, content):
    path = tmp_path / "targets.yaml"
    path.write_text(content)
    return path


def test_load_targets_applies_default_cap(tmp_path):
    path = _write(tmp_path, VALID_YAML)
    targets = load_targets(path)
    assert targets[0]["max_errors_per_run"] == 5


def test_load_targets_respects_explicit_cap(tmp_path):
    path = _write(tmp_path, VALID_YAML_WITH_CAP)
    targets = load_targets(path)
    assert targets[0]["max_errors_per_run"] == 2


def test_load_targets_missing_required_field_raises(tmp_path):
    path = _write(tmp_path, MISSING_FIELD_YAML)
    with pytest.raises(ValueError, match="repo"):
        load_targets(path)


def test_load_targets_placeholder_channel_id_raises(tmp_path):
    path = _write(tmp_path, PLACEHOLDER_YAML)
    with pytest.raises(ValueError, match="placeholder"):
        load_targets(path)


def test_load_targets_empty_raises(tmp_path):
    path = _write(tmp_path, EMPTY_YAML)
    with pytest.raises(ValueError, match="No targets"):
        load_targets(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_load_targets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.load_targets'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/load_targets.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_load_targets.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Write the real `targets.yaml`**

```yaml
# Fill in slack_channel_id and repo (org/name) before the first real run.
# See README.md "Prerequisites" for what's needed.
targets:
  - name: backend-server-master
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: REPLACE_ME_ORG/backend-server
    branch: master
  - name: backend-server-total-media
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: REPLACE_ME_ORG/backend-server
    branch: total-media-master
  - name: frontend-b2b
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: REPLACE_ME_ORG/frontend-b2b
    branch: master
  - name: frontend-b2c
    slack_channel_id: REPLACE_ME_SLACK_CHANNEL_ID
    repo: REPLACE_ME_ORG/frontend-b2c
    branch: main
```

- [ ] **Step 6: Commit**

```bash
git add scripts/load_targets.py targets.yaml tests/test_load_targets.py
git commit -m "Add target loader with validation"
```

---

### Task 3: Cursor store (`scripts/cursor_store.py`)

**Files:**
- Create: `scripts/cursor_store.py`
- Test: `tests/test_cursor_store.py`

**Interfaces:**
- Consumes: nothing
- Produces: `load_cursors(path) -> dict[str, str]`, `get_cursor(cursors: dict, target_name: str) -> str | None`, `set_cursor(cursors: dict, target_name: str, timestamp: str) -> dict[str, str]` (returns a new dict, does not mutate input), `save_cursors(path, cursors: dict) -> None`. CLI: `python3 scripts/cursor_store.py get <path> <target_name>` prints the cursor or an empty line; `python3 scripts/cursor_store.py set <path> <target_name> <timestamp>` persists it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cursor_store.py
import json

from scripts.cursor_store import get_cursor, load_cursors, save_cursors, set_cursor


def test_load_cursors_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "cursors.json"
    assert load_cursors(path) == {}


def test_set_cursor_does_not_mutate_input():
    original = {"a": "100"}
    updated = set_cursor(original, "b", "200")
    assert original == {"a": "100"}
    assert updated == {"a": "100", "b": "200"}


def test_get_cursor_unknown_target_returns_none():
    assert get_cursor({"a": "100"}, "unknown") is None


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "cursors.json"
    cursors = set_cursor({}, "frontend-b2c", "1717000000.000100")
    save_cursors(path, cursors)

    loaded = load_cursors(path)

    assert loaded == {"frontend-b2c": "1717000000.000100"}
    assert json.loads(path.read_text()) == {"frontend-b2c": "1717000000.000100"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cursor_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.cursor_store'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/cursor_store.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cursor_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/cursor_store.py tests/test_cursor_store.py
git commit -m "Add cursor state store"
```

---

### Task 4: Signature builder (`scripts/build_signature.py`)

**Files:**
- Create: `scripts/build_signature.py`
- Test: `tests/test_build_signature.py`

**Interfaces:**
- Consumes: nothing
- Produces: `build_signature(exception_type: str, frames: list[str]) -> str` — deterministic, lowercase, `[a-z0-9-]+` only, `<= 50` chars, format `<slug>-<12-hex-char-hash>`. CLI: `python3 scripts/build_signature.py <exception_type> <frame1> [frame2]` prints the signature.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_build_signature.py
import re

from scripts.build_signature import build_signature


def test_same_input_produces_same_signature():
    sig1 = build_signature("NullPointerException", ["UserService.java:42"])
    sig2 = build_signature("NullPointerException", ["UserService.java:42"])
    assert sig1 == sig2


def test_different_frames_produce_different_signatures():
    sig1 = build_signature("NullPointerException", ["UserService.java:42"])
    sig2 = build_signature("NullPointerException", ["UserService.java:99"])
    assert sig1 != sig2


def test_signature_is_branch_name_safe():
    sig = build_signature("Null Pointer: Exception!!", ["Some Weird File.java:1"])
    assert re.fullmatch(r"[a-z0-9-]+", sig)


def test_signature_is_length_bounded():
    sig = build_signature("A" * 200, ["B" * 200 + ".java:1"])
    assert len(sig) <= 50


def test_signature_includes_hash_suffix():
    sig = build_signature("TimeoutError", ["worker.py:10"])
    _, _, suffix = sig.rpartition("-")
    assert len(suffix) == 12
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_signature.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.build_signature'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/build_signature.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_signature.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/build_signature.py tests/test_build_signature.py
git commit -m "Add deterministic error signature builder"
```

---

### Task 5: Daily-run instructions (`AGENT.md`)

**Files:**
- Create: `AGENT.md`

**Interfaces:**
- Consumes: `load_targets` CLI (Task 2), `cursor_store` CLI (Task 3), `build_signature` CLI (Task 4) — all invoked as documented shell commands, not imported.
- Produces: the runbook that the `/schedule` routine (Task 7) executes verbatim as its prompt.

- [ ] **Step 1: Write `AGENT.md`**

```markdown
# Error Triage Agent — Daily Run Instructions

Once a day, triage new error messages posted to 4 Slack channels (one per
deployment target), investigate root cause, and either open a PR with a
tested fix or reply in the Slack thread with findings.

## Environment

- `SLACK_BOT_TOKEN` — bot token with `channels:history` and `chat:write`
  scopes on the 4 target channels and the report channel.
- `ERROR_TRIAGE_REPORT_CHANNEL_ID` — Slack channel ID for
  `#error-triage-agent`.
- `DRY_RUN` — optional, `"true"` or unset. When `"true"`, never push
  branches, open PRs, or post to target-channel Slack threads; log intended
  actions to the report channel instead, each line prefixed `[DRY RUN]`.
- `DRY_RUN_FIXTURE` — optional, path to a JSON file of fixture Slack
  messages (`{"messages": [{"ts": "...", "text": "..."}]}`, see
  `tests/fixtures/sample_slack_messages.json`). When set, use this file's
  `messages` array instead of calling the Slack API for every target's
  fetch step — used only for local validation.

## Steps

1. Load targets: `python3 scripts/load_targets.py targets.yaml`. Parse the
   JSON array; each object has `name`, `slack_channel_id`, `repo`,
   `branch`, `max_errors_per_run`.

2. For each target, in the order given by `targets.yaml`:

   a. **Get the cursor:**
      `python3 scripts/cursor_store.py get state/cursors.json <name>`
      If the output is empty (no cursor yet — first run for this channel),
      treat this as "start from now": use the current UTC epoch seconds as
      the cursor for this run and skip straight to step (f) with zero
      messages — never backfill full channel history.

   b. **Fetch new messages**, oldest first:
      - If `DRY_RUN_FIXTURE` is set: read `messages` from that file.
      - Otherwise:
        `curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" "https://slack.com/api/conversations.history?channel=<slack_channel_id>&oldest=<cursor>"`
        and take the `messages` array from the JSON response.
      - If there are no new messages, go to step (f) with zero messages.

   c. **Cap the batch** to `max_errors_per_run` (oldest first). Anything
      beyond the cap is left for tomorrow — do not advance the cursor past
      the last message actually processed in step (f).

   d. For each message in the capped batch, wrapped in its own
      try/catch so one message's failure never stops the rest of this
      target's batch:

      - Parse the exception type and the top 1-2 `file:line` stack frames
        from the message text.
      - Compute the signature:
        `python3 scripts/build_signature.py "<exception_type>" "<frame1>" ["<frame2>"]`
      - **Dedup check** — skip this message entirely (no PR, no Slack
        reply) if either matches:
        - `gh search prs --repo <repo> --state open "<signature>"` returns
          a result, or
        - `gh api repos/<repo>/branches --jq '.[].name'` contains a line
          equal to `autofix/<signature>`.
      - **Investigate:** clone `<repo>` at `<branch>` into a scratch
        directory (`git clone --branch <branch> --single-branch
        <repo-url> <scratch-dir>`), then use the stack trace to locate the
        offending code and read enough surrounding context to form a
        root-cause hypothesis. Confirm the hypothesis against the actual
        code before proposing a fix — do not guess.
      - **Decide confidence.** You have a confident fix only if you can
        point to the specific lines causing the behavior described by the
        exception/stack trace, and the fix is a direct correction of that
        cause (not a speculative workaround).
      - **If confident:**
        - Branch: `git checkout -b autofix/<signature>`.
        - Implement the minimal fix.
        - Add a regression test reproducing the original error, if the
          repo's existing test setup makes this feasible.
        - Run the relevant existing test suite for the changed area.
        - If tests pass: push the branch and open the PR (in `DRY_RUN`,
          skip the push/PR and instead log the intended title/body to the
          report channel prefixed `[DRY RUN]`):
          ```
          gh pr create --repo <repo> --base <branch> --head autofix/<signature> \
            --title "[auto-fix] <short exception summary>" \
            --body "<body>" --reviewer jspiliot
          ```
          The PR body must include: (1) the original Slack error text and
          a link to the message, (2) root-cause explanation, (3) what the
          fix changes and why, (4) test/verification results.
        - If tests fail and cannot be resolved with reasonable effort:
          treat as **not confident** — fall through to the next bullet.
          Never open a PR with failing tests.
      - **If not confident (or tests failed):** reply in the original
        Slack thread (in `DRY_RUN`, skip the real post and log it to the
        report channel instead, prefixed `[DRY RUN]`):
        ```
        curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
          -H "Content-type: application/json" \
          --data '{"channel":"<slack_channel_id>","thread_ts":"<message ts>","text":"<summary>"}' \
          https://slack.com/api/chat.postMessage
        ```
        The summary must include: root-cause hypothesis (or "could not
        determine"), files/areas examined, and why no PR was opened.
      - Clean up the scratch clone.

   e. If any unhandled error occurs for this target as a whole (clone
      failure, Slack/GitHub API error, etc.), log it, leave this target's
      cursor unchanged so it's retried next run, and move on to the next
      target — never let one target's failure stop the run.

   f. Update this target's cursor to the timestamp of the last message
      actually processed (or "now" if none were processed):
      `python3 scripts/cursor_store.py set state/cursors.json <name> <timestamp>`

3. After all targets are processed, commit the updated state (in
   `DRY_RUN`, show the diff instead of committing/pushing):
   ```
   git add state/cursors.json
   git commit -m "Update cursors after daily run"
   git push
   ```

4. Post a daily summary to `ERROR_TRIAGE_REPORT_CHANNEL_ID`: per target,
   how many new errors were seen, how many PRs were opened (with links),
   how many got a Slack-only reply, and how many were skipped as
   duplicates.

5. **Run-level failures** — anything not scoped to a single target (bad
   `SLACK_BOT_TOKEN`, `gh` not authenticated, etc.) — abort the run
   immediately and post an alert to `ERROR_TRIAGE_REPORT_CHANNEL_ID`
   describing what failed, instead of continuing.

## Non-negotiables

- Never commit or push directly to `master`/`main`/`total-media-master` —
  every fix goes through a PR.
- Never open a PR with failing tests.
- Never skip the dedup check.
- No area of the codebase is off-limits for a fix — the PR review is the
  safety net, not a denylist.
```

- [ ] **Step 2: Verify structure**

Run: `grep -c "^## " AGENT.md`
Expected: `3`

- [ ] **Step 3: Commit**

```bash
git add AGENT.md
git commit -m "Add daily-run instructions for the error triage agent"
```

---

### Task 6: Dry-run fixture and validation walkthrough

**Files:**
- Create: `tests/fixtures/sample_slack_messages.json`

**Interfaces:**
- Consumes: `build_signature` CLI (Task 4), `cursor_store` CLI (Task 3)
- Produces: a fixture usable with `AGENT.md`'s `DRY_RUN_FIXTURE` for manual validation (Task 7 uses this before going live).

- [ ] **Step 1: Write the fixture**

```json
{
  "messages": [
    {
      "ts": "1720512000.000100",
      "text": "NullPointerException: Cannot read property 'id' of undefined\n  at UserController.getProfile (src/controllers/UserController.js:42)\n  at Router.handle (src/router.js:88)"
    }
  ]
}
```

- [ ] **Step 2: Verify the signature CLI is deterministic against this fixture's error**

Run (twice):
```bash
python3 scripts/build_signature.py "NullPointerException" "UserController.js:42"
```
Expected: identical single-line output both times, matching `^[a-z0-9-]+-[0-9a-f]{12}$` (e.g. `nullpointerexception-<12 hex chars>`).

- [ ] **Step 3: Verify the cursor CLI round-trips on a scratch copy**

Run:
```bash
cp state/cursors.json /tmp/cursors-test.json
python3 scripts/cursor_store.py set /tmp/cursors-test.json frontend-b2c 1720512000.000100
python3 scripts/cursor_store.py get /tmp/cursors-test.json frontend-b2c
```
Expected final line of output: `1720512000.000100`

- [ ] **Step 4: Document the manual LLM dry-run checklist**

This step has no code — it records what "done" looks like for Task 7's dry
run. Once real Slack/GitHub credentials exist (Task 7), run the scheduled
routine manually via `/schedule`'s "run now" with `DRY_RUN=true` and
`DRY_RUN_FIXTURE=tests/fixtures/sample_slack_messages.json`, then confirm
in the transcript and in `#error-triage-agent`:
- A signature was computed for the fixture's `NullPointerException`.
- The dedup `gh search prs` / branch check ran before any fix attempt.
- No `git push`, `gh pr create`, or real `chat.postMessage` to a target
  channel occurred.
- A `[DRY RUN]` summary was posted to `#error-triage-agent` describing the
  intended action (PR or Slack reply) for the fixture message.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sample_slack_messages.json
git commit -m "Add dry-run fixture for manual validation"
```

---

### Task 7: Register the daily schedule and go live

**Files:**
- Modify: `targets.yaml` (replace `REPLACE_ME_*` placeholders with real values)

**Interfaces:**
- Consumes: `AGENT.md` (Task 5) as the routine's prompt, `targets.yaml` (Task 2) filled in with real values, `tests/fixtures/sample_slack_messages.json` (Task 6) for the pre-flight dry run.
- Produces: a live daily `/schedule` routine.

- [ ] **Step 1: Gather external prerequisites**

These are not code changes — confirm each before continuing:
- Slack bot token obtained (`SLACK_BOT_TOKEN`), with `channels:history` +
  `chat:write` scopes, invited into all 4 target channels.
- `#error-triage-agent` channel created in Slack, bot invited, channel ID
  noted (`ERROR_TRIAGE_REPORT_CHANNEL_ID`).
- The 4 target channel IDs noted.
- `gh auth status` confirms push + PR-create access to `backend-server`,
  `frontend-b2b`, and `frontend-b2c` from the environment that will run
  the schedule.

- [ ] **Step 2: Fill in `targets.yaml`**

Replace every `REPLACE_ME_SLACK_CHANNEL_ID` and `REPLACE_ME_ORG` in
`targets.yaml` with the real values gathered in Step 1.

Run: `python3 scripts/load_targets.py targets.yaml`
Expected: prints a JSON array of 4 targets with no `ValueError`.

- [ ] **Step 3: Commit the filled-in config**

```bash
git add targets.yaml
git commit -m "Fill in real Slack channel IDs and repo names"
```

- [ ] **Step 4: Register the scheduled routine**

Use the `schedule` skill to create a routine named
`error-triage-agent-daily`, cron `0 6 * * *`, prompt set to the contents of
`AGENT.md`, with `SLACK_BOT_TOKEN` and `ERROR_TRIAGE_REPORT_CHANNEL_ID`
configured as its environment/secrets.

- [ ] **Step 5: Pre-flight dry run against real channels**

Trigger a manual "run now" via the `schedule` skill with `DRY_RUN=true`
(no `DRY_RUN_FIXTURE` this time — real channel backlog). Confirm in
`#error-triage-agent` that the summary looks sane against whatever is
currently in the 4 channels.

- [ ] **Step 6: One real end-to-end run, then enable the daily cron**

Trigger one manual "run now" with `DRY_RUN` unset. Confirm a real PR or
Slack-thread reply was produced correctly for at least one error (if any
are pending), then leave the daily `0 6 * * *` schedule enabled going
forward.
```
