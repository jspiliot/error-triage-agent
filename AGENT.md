# Error Triage Agent — Daily Run Instructions

Once a day, triage new error messages posted to 4 Slack channels (one per
deployment target), investigate root cause, and either open a merge
request (MR) with a tested fix or reply in the Slack thread with findings.

Target repos live on GitLab (`gitlab.com/adadot/...`). All GitLab
interaction uses the REST API directly via `curl` and `PRIVATE-TOKEN` auth
— there is no `glab` CLI dependency.

## Environment

- `SLACK_BOT_TOKEN` — bot token with `channels:history` and `chat:write`
  scopes on the 4 target channels and the report channel.
- `ERROR_TRIAGE_REPORT_CHANNEL_ID` — Slack channel ID for
  `#error-triage-agent`.
- `GITLAB_TOKEN` — Personal Access Token (`api` + `write_repository`
  scopes) used for both the REST API calls below and for git clone/push
  over HTTPS.
- `GITLAB_REVIEWER_USERNAME` — GitLab username to request as MR reviewer
  (currently `j.spiliot`).
- `GITHUB_TOKEN` — Personal Access Token (`repo` scope) with write access
  to *this* repo (`error-triage-agent` itself, not the GitLab targets).
  The platform's built-in GitHub source checkout is read-only, so pushing
  the updated `state/cursors.json` back (step 3) requires this separate
  credential over HTTPS, the same pattern as `GITLAB_TOKEN`.
- `DRY_RUN` — optional, `"true"` or unset. When `"true"`, never push
  branches, open MRs, or post to target-channel Slack threads; log
  intended actions to the report channel instead, each line prefixed
  `[DRY RUN]`.
- `DRY_RUN_FIXTURE` — optional, path to a JSON file of fixture Slack
  messages (`{"messages": [{"ts": "...", "text": "..."}]}`, see
  `tests/fixtures/sample_slack_messages.json`). When set, use this file's
  `messages` array instead of calling the Slack API for every target's
  fetch step — used only for local validation.

## GitLab REST API conventions

Every target's `repo` field (e.g. `adadot/backend-server`) needs
URL-encoding for the GitLab API's `:id` path segment (these paths have
exactly one `/`, so a plain substitution is safe):

```bash
project_path_encoded=$(echo "<repo>" | sed 's/\//%2F/g')
```

Resolve the reviewer's GitLab user ID once at the start of the run (reused
for every MR this run creates):

```bash
reviewer_id=$(curl -s --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/users?username=$GITLAB_REVIEWER_USERNAME" | jq -r '.[0].id')
```

## Steps

1. Load targets: `python3 scripts/load_targets.py targets.yaml`. Parse the
   JSON array; each object has `name`, `slack_channel_id`, `repo`,
   `branch`, `max_errors_per_run`.

2. Resolve `reviewer_id` (see above) — abort the run (see step 5) if this
   lookup fails, since every MR needs it.

3. For each target, in the order given by `targets.yaml`:

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
      - **Dedup check** — skip this message entirely (no MR, no Slack
        reply) if either matches:
        - `curl -s --header "PRIVATE-TOKEN: $GITLAB_TOKEN" "https://gitlab.com/api/v4/projects/$project_path_encoded/merge_requests?state=opened&search=<signature>"`
          returns a non-empty JSON array, or
        - `curl -s --header "PRIVATE-TOKEN: $GITLAB_TOKEN" "https://gitlab.com/api/v4/projects/$project_path_encoded/repository/branches?search=autofix/<signature>"`
          returns a non-empty JSON array.
      - **Investigate:** clone `<repo>` at `<branch>` into a scratch
        directory:
        `git clone --branch <branch> --single-branch "https://oauth2:$GITLAB_TOKEN@gitlab.com/<repo>.git" <scratch-dir>`
        then use the stack trace to locate the offending code and read
        enough surrounding context to form a root-cause hypothesis.
        Confirm the hypothesis against the actual code before proposing a
        fix — do not guess.
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
        - If tests pass: push the branch and open the MR (in `DRY_RUN`,
          skip the push/MR and instead log the intended title/description
          to the report channel prefixed `[DRY RUN]`):
          ```bash
          git push origin autofix/<signature>
          curl -s --request POST --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
            --header "Content-Type: application/json" \
            --data '{
              "source_branch": "autofix/<signature>",
              "target_branch": "<branch>",
              "title": "[auto-fix] <short exception summary>",
              "description": "<body>",
              "reviewer_ids": ['"$reviewer_id"'],
              "remove_source_branch": true
            }' \
            "https://gitlab.com/api/v4/projects/$project_path_encoded/merge_requests"
          ```
          The MR description must include: (1) the original Slack error
          text and a link to the message, (2) root-cause explanation, (3)
          what the fix changes and why, (4) test/verification results.
        - If tests fail and cannot be resolved with reasonable effort:
          treat as **not confident** — fall through to the next bullet.
          Never open an MR with failing tests.
      - **If not confident (or tests failed):** reply in the original
        Slack thread (in `DRY_RUN`, skip the real post and log it to the
        report channel instead, prefixed `[DRY RUN]`):
        ```bash
        curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
          -H "Content-type: application/json" \
          --data '{"channel":"<slack_channel_id>","thread_ts":"<message ts>","text":"<summary>"}' \
          https://slack.com/api/chat.postMessage
        ```
        The summary must include: root-cause hypothesis (or "could not
        determine"), files/areas examined, and why no MR was opened.
      - Clean up the scratch clone.

   e. If any unhandled error occurs for this target as a whole (clone
      failure, Slack/GitLab API error, etc.), log it, leave this target's
      cursor unchanged so it's retried next run, and move on to the next
      target — never let one target's failure stop the run.

   f. Update this target's cursor to the timestamp of the last message
      actually processed (or "now" if none were processed):
      `python3 scripts/cursor_store.py set state/cursors.json <name> <timestamp>`

4. After all targets are processed, persist the updated state (in
   `DRY_RUN`, show the diff instead — skip the rest of this step). Do not
   rely on a bare `git push` to `main`: the platform's own checkout of
   this repo is read-only, and sessions have been observed silently
   redirecting direct-to-`main` pushes onto a `claude/*` branch instead —
   so push to a dedicated branch and merge it via the GitHub REST API
   explicitly, using `GITHUB_TOKEN`, rather than assuming the push lands
   where asked:
   ```bash
   git checkout -b "state-update/$(date -u +%Y%m%d-%H%M%S)"
   git add state/cursors.json
   git commit -m "Update cursors after daily run"
   branch=$(git branch --show-current)
   git push "https://${GITHUB_TOKEN}@github.com/jspiliot/error-triage-agent.git" "HEAD:$branch"

   pr_number=$(curl -s --request POST \
     -H "Authorization: token ${GITHUB_TOKEN}" \
     -H "Accept: application/vnd.github+json" \
     --data "{\"title\":\"Update cursors after daily run\",\"head\":\"$branch\",\"base\":\"main\"}" \
     "https://api.github.com/repos/jspiliot/error-triage-agent/pulls" | jq -r '.number')

   curl -s --request PUT \
     -H "Authorization: token ${GITHUB_TOKEN}" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/jspiliot/error-triage-agent/pulls/${pr_number}/merge"
   ```
   This is pure bookkeeping (not user-facing code), so merge it
   immediately — no human review needed for a cursor-only change. If any
   step here fails (push, PR creation, or merge), do not treat it as
   fatal to the run's own findings (MRs/Slack replies already happened
   for real), but report it clearly in the daily summary (step 5) so the
   cursor loss is visible rather than silent, including the cursor values
   that failed to persist so they can be applied manually.

5. Post a daily summary to `ERROR_TRIAGE_REPORT_CHANNEL_ID`. Keep it short
   — this is a Slack message, not a run log:
   - **Nothing happened anywhere** (no new errors, no MRs, no replies, no
     duplicates skipped, across all targets): post exactly one line, e.g.
     `✅ <date> — no new errors across all N targets.` Do not list targets
     individually, do not mention cursors, reviewer resolution, or
     DRY_RUN diff details — none of that belongs in the Slack summary.
   - **Something happened somewhere:** post one line per target that had
     any activity (new errors, MRs, replies, or duplicates > 0), and
     *omit* targets with zero activity entirely — don't pad the message
     with "no activity" lines for quiet targets. Each active target's
     line: `<target>: <N> new, <M> MR(s) opened <links>, <R> replied,
     <D> duplicate(s) skipped.` Only include the sub-counts that are
     non-zero.
   - In `DRY_RUN`, prefix the whole message `[DRY RUN]` once at the top
     rather than repeating it per line.

6. **Run-level failures** — anything not scoped to a single target (bad
   `SLACK_BOT_TOKEN`, bad `GITLAB_TOKEN`, reviewer lookup failure, etc.) —
   abort the run immediately and post an alert to
   `ERROR_TRIAGE_REPORT_CHANNEL_ID` describing what failed, instead of
   continuing.

## Non-negotiables

- Never commit or push directly to `master`/`main`/`total-media-master` —
  every fix goes through an MR.
- Never open an MR with failing tests.
- Never skip the dedup check.
- No area of the codebase is off-limits for a fix — MR review is the
  safety net, not a denylist.
