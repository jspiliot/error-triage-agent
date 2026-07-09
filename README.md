# error-triage-agent

Daily Claude Code scheduled routine that reads error logs posted to Slack
for 4 deployment targets (GitLab repos under `gitlab.com/adadot`),
investigates root causes, and opens a merge request (MR) with a tested fix
when confident — or replies in the Slack thread with its findings when it
isn't.

## Prerequisites

Before the daily schedule can run for real, gather:

- A Slack bot token (`SLACK_BOT_TOKEN`) with `channels:history` and
  `chat:write` scopes, invited into all 5 channels below. (Use a dedicated
  Slack app for this bot if your main app can't add `chat:write`.)
- The 4 target channel IDs (one per row in `targets.yaml`).
- A new `#error-triage-agent` Slack channel, with the bot invited, and its
  channel ID (`ERROR_TRIAGE_REPORT_CHANNEL_ID`).
- A GitLab Personal Access Token (`GITLAB_TOKEN`, `api` +
  `write_repository` scopes) with Developer+ access to `backend-server`,
  `frontend-b2b`, and `frontend-b2c`. (Group/Project Access Tokens are
  preferred for isolation but may be disabled by org policy — a Personal
  Access Token is the fallback.)
- The GitLab username to request as MR reviewer
  (`GITLAB_REVIEWER_USERNAME`).

## Setup

1. `pip install -r requirements.txt`
2. Fill in the `REPLACE_ME_*` values in `targets.yaml` with the real Slack
   channel IDs and `org/repo` names.
3. Run `pytest` — all helper-script tests should pass.

## How the daily run works

`AGENT.md` is the runbook a Claude Code `/schedule` routine executes once a
day. See that file for the full step-by-step flow. In short: for each of
the 4 targets, it fetches new Slack messages, skips ones already handled
(via a GitLab MR/branch dedup check), investigates root cause, and either
opens an MR or replies in the Slack thread.

## Dry-run validation

`AGENT.md` supports `DRY_RUN=true` (no pushes/MRs/real Slack replies — logs
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
