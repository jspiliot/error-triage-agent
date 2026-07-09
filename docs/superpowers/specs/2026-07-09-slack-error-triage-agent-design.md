# Slack Error Triage Agent — Design

Date: 2026-07-09

> **Correction (2026-07-10):** the target repos are on **GitLab**
> (`gitlab.com/adadot/...`), not GitHub. Everywhere below that says `gh`,
> "GitHub", or "PR", the actual implementation (`AGENT.md`) uses GitLab's
> REST API via `curl` + `PRIVATE-TOKEN` auth and opens **merge requests**
> instead. This document is left otherwise unchanged as a historical
> record of the original design reasoning — `AGENT.md` and `README.md` in
> this repo are the source of truth for current behavior.

## Purpose

A daily scheduled Claude agent that reads error logs posted to Slack for 4
deployment targets, investigates root causes, and — when confident — opens a
PR with a tested fix. When not confident, it posts its investigation findings
back to the originating Slack thread instead of guessing.

## Targets

Four (Slack channel → repo, branch) pairs, each treated independently:

1. `backend-server` @ `master`
2. `backend-server` @ `total-media-master` (separate deploy of the same repo
   to a different system)
3. `frontend-b2b` @ `master`
4. `frontend-b2c` @ `main`

Slack messages in each channel contain an error message plus a stack trace
(confirmed format — not just a bare summary).

## Execution model

- Runs as a single Claude Code `/schedule` cloud routine, once daily at
  06:00 UTC.
- Runs even if the developer's laptop is off; clones each repo fresh from
  GitHub each run.
- Wall-clock time is not a constraint (daily cadence) — the 4 targets are
  processed **sequentially**, not in parallel. This keeps the design to one
  prompt, one state file, and one schedule entry.

## Repo layout (`error-triage-agent`)

```
error-triage-agent/
  AGENT.md            # instructions run by the scheduled routine
  targets.yaml         # the 4 (slack_channel, repo, branch) mappings, incl. per-target caps
  state/
    cursors.json        # last-processed Slack timestamp, per channel
  README.md
```

`targets.yaml` fields per target: `name`, `slack_channel_id`, `repo`,
`branch`, `max_errors_per_run` (default 5).

`state/cursors.json` holds only per-channel last-read timestamps. Dedup
against already-handled errors is done live via GitHub search each run, not
via a stored index.

## Components

1. **Slack fetcher** — `conversations.history` for the target's channel,
   filtered to messages after the stored cursor. Auth via existing Slack
   app's bot token (env var/secret on the scheduled routine).
2. **Signature builder** — derives a stable signature per error from
   exception type + top 1-2 stack frames (file:line). Used as dedup search
   text only, not persisted.
3. **Dedup check** — `gh search prs --repo <repo> "<signature>" --state open`
   plus a branch-name fallback check. Skip the error if a match is found.
4. **Investigator** — clones `repo@branch` into a scratch worktree, uses the
   stack trace to locate the offending code and forms a root-cause
   hypothesis (systematic-debugging style, not guess-and-check).
5. **Fixer + verifier** — if a confident fix is found: implement on a new
   branch (`autofix/<signature-short>`), run the existing relevant test
   suite, add a regression test reproducing the original error where
   feasible, re-run tests.
6. **Outcome handler**:
   - Tests pass → `gh pr create`, ready-for-review, `jspiliot` as reviewer,
     title prefixed `[auto-fix]`, body = bug summary + root cause + fix +
     link to the original Slack message.
   - No confident fix, or tests fail and can't be resolved → reply in the
     original Slack thread with the investigation summary (root cause
     hypothesis, affected files, why no PR was opened).
7. **Cursor updater** — after all targets are processed, commits the updated
   `state/cursors.json` back to `error-triage-agent` (direct commit to
   `main` — this is the agent's own bookkeeping, not product code).

## Data flow (one daily run)

```
1. /schedule fires AGENT.md at 06:00 UTC
2. Load targets.yaml and state/cursors.json
3. FOR each target in targets.yaml (sequential):
     TRY:
       a. Fetch new Slack messages since this target's cursor
       b. IF none → advance cursor, continue
       c. FOR each new error message (oldest first, capped at max_errors_per_run):
            i.   Build signature
            ii.  Dedup check via gh — skip to next error if matched
            iii. Clone repo@branch into scratch worktree, investigate
            iv.  IF confident fix found: implement, test, add regression
                 test → PR if tests pass, else fall through to (v)
                 ELSE: reply in Slack thread with findings
            vi.  Clean up scratch worktree
       d. Advance this target's cursor to the last message actually processed
     CATCH (unhandled failure for this target):
       - log it, leave cursor unchanged (retried next run), continue to next target
4. Commit updated state/cursors.json (single commit, end of run)
5. Post daily summary (errors seen / PRs opened / Slack-only replies, per
   target) to #error-triage-agent
```

A hard failure on one target never blocks the other three.

## Guardrails

- **First-ever run per channel**: cursor initializes to "now", not full
  channel history — avoids a backfill flood of PRs on day one.
- **Per-error isolation**: each error within a target is individually
  try/caught; one error's failure doesn't stop the rest of that target's
  batch.
- **Runaway cap**: `max_errors_per_run` (default 5) per target per run.
  Excess messages are left for the next run (cursor only advances past what
  was actually processed).
- **No sensitive-area denylist** — the agent may propose fixes anywhere in
  the repo. Human review on the PR is the correctness/safety net, backed by
  the test + regression-test verification step.
- **Credential/infra failures** (bad Slack token, GitHub auth failure, etc.)
  abort the whole run immediately (these indicate the agent itself is
  broken) and post an alert to `#error-triage-agent`, rather than being
  treated as a per-error skip.

## Self-reporting

A dedicated `#error-triage-agent` Slack channel receives:
- Run-level failure alerts (bad auth, infra errors) — immediate.
- A daily summary per run: errors seen, PRs opened, Slack-only replies, per
  target.

## Testing / validating the agent

- **Dry-run mode**: `AGENT.md` supports `DRY_RUN=true` (settable via
  `/schedule`'s manual "run now"). Does everything except push branches,
  open PRs, or post Slack replies — logs intended actions to
  `#error-triage-agent` instead.
- Before enabling the daily schedule, do one manual dry run against each
  channel's real current backlog to validate signature/dedup logic and
  investigation quality.
- Ongoing signal is the daily summary — if PR quality drifts, pause the
  schedule via `/schedule`.
- No unit-test suite for the agent itself (it is a prompt-driven routine,
  not a code library); correctness is validated by dry-run + mandatory human
  PR review.

## Open items (need values before implementation, not design decisions)

- Slack bot token and the 4 channel IDs.
- `#error-triage-agent` channel ID (needs to be created).
- GitHub repo names/org for `backend-server`, `frontend-b2b`, `frontend-b2c`.
- Confirm the scheduled routine has `gh` push/PR-create access to all 3
  repos (2 branches for `backend-server`).
