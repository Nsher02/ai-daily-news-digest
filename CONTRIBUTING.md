# Contributing to AI Daily News Digest

This public repository is also the production codebase for a daily email automation. Changes can affect story selection, AI usage, saved delivery state, and real email. The [README](README.md) explains the system and its configuration; this guide explains how to change it safely.

## Scope and boundaries

- Make changes on a `codex/` branch and open a PR targeting `main`, including for documentation and dependency updates.
- Preserve existing implementation prompts and design images. Do not publish credentials, personal replay snapshots, `.env`, or decrypted state.
- Keep delivery schedules, provider settings, and monitor behavior unchanged unless the task explicitly calls for those changes.
- Do not send test emails, dispatch delivery workflows, run the mail-capable Google monitor, or make live provider calls without explicit authorization for the task.
- Use a GitHub noreply address for commits if you want to keep your personal email out of new commit metadata. Changing this setting does not edit old commits.

The project has no automatic PR merging. Dependabot proposes dependency updates; they follow the same review and test requirements as other changes.

## Prepare a checkout

Use Python 3.13, Node.js 22, Git, and an authenticated GitHub CLI for maintainers who will open and merge PRs.

```sh
git clone https://github.com/Nsher02/ai-daily-news-digest.git
cd ai-daily-news-digest
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Before committing, set the email for this repository only:

```sh
git config --local user.email "YOUR_GITHUB_NOREPLY_ADDRESS"
```

Copy your address from GitHub's account email settings. Do not change a global identity used for unrelated projects.

If no custom hooks would be displaced, install the local direct-push safeguard:

```sh
git config --local core.hooksPath .githooks
```

The hook blocks direct pushes, force pushes, and deletions targeting `main`. It is a checkout-local safeguard, not a replacement for GitHub branch protection; it must be installed in each new clone.

## Make and validate a change

1. Start from current `main`:

   ```sh
   git switch main
   git pull --ff-only origin main
   git switch -c codex/describe-the-change
   ```

2. Implement a focused change. Update documentation when behavior or configuration changes. Keep unrelated edits out of the PR and inspect `git diff` for accidental private data.
3. Run checks appropriate to the change. The complete offline checks are:

   ```sh
   .venv/bin/python -m unittest discover -s tests -v
   node tests/test_google_apps_script.cjs
   node --check < monitoring/google_apps_script.gs
   python3 -m json.tool monitoring/appsscript.json > /dev/null
   git diff --check
   ```

   Installation needs network access; these tests use mocked services. Documentation-only edits need content/link review and whitespace checks, with the required hosted regression job still passing before merge. A replay of `tests/fixtures/replay.json` is safe for offline rendering. A dry run or Groq verification uses live services even if it sends no email.
4. Commit with a concise, specific message, push the branch, and open a PR. Use the [PR template](.github/pull_request_template.md) to explain the problem, resulting behavior, validation, and any relevant limits.
5. Wait for **Automated tests / Offline regression tests** on the current PR commit. A previous commit's green result, a push-only run, or a skipped job is insufficient for the merge helper.
6. If `main` changes, update the PR branch with a merge, resolve conflicts, push, and wait for the new PR checks:

   ```sh
   git fetch origin
   git merge origin/main
   git push
   ```

## Merge an authorized PR

From the checkout, use:

```sh
python3 scripts/merge_pr.py NUMBER --check-only
python3 scripts/merge_pr.py NUMBER
```

Replace `NUMBER` with the authorized PR number. The helper verifies an open, non-draft, same-repository PR targeting `main`; the latest PR-event run for the exact head commit and its **Offline regression tests** job must both have completed successfully. It also checks that the branch includes current `main`, rereads both refs, and pins the checked head when requesting a squash merge.

Never bypass failed or missing checks, use an administrator override, or force-push `main`. Do not merge an unrelated PR simply because its tests pass. Outside-fork contributions need maintainer review; the merge helper intentionally rejects cross-repository PRs rather than running an automatic privileged merge path.

After merging:

```sh
git switch main
git pull --ff-only origin main
```

Delete the feature branch when it is no longer needed. A merge can trigger offline CI; it is not permission to dispatch delivery or send a test email.

## Repository protections and private data

The public repository's `main` protection requires a PR, passing **Offline regression tests** from GitHub Actions, an up-to-date branch, and resolved review conversations. It applies to administrators, blocks force pushes and deletions, and does not require another person's approval for the owner's PRs. Keep those protections enabled.

Workflow defaults are read-only, permitted actions are SHA-pinned, and checkouts discard persisted credentials. Outside contributors' workflows require approval. Push/PR regression tests receive no AI or SMTP secrets. Secret scanning and push protection help catch supported credential patterns, but do not replace review.

Repository settings, secrets, scheduler tokens, and the live Google monitor are not installed by cloning. A fork or new repository needs its own configuration. Never reset or edit encrypted delivery state to force a resend, and never treat SMTP acceptance as proof of inbox delivery. Use the [encrypted-state guide](docs/encrypted-state.md) and [monitor instructions](monitoring/README.md) for authorized maintenance.

Report potential credential leaks or vulnerabilities through GitHub's private vulnerability-reporting option, not a public issue containing sensitive values. Keep encryption keys and recovery copies in private storage. Historical audits document what was checked at a particular time; they do not certify future changes.
