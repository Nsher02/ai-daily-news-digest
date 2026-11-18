# Make changes through tested pull requests

Keep this repository free and private. Every change, including documentation and dependency updates, should go through a pull request. This is the working process for the owner and coding agents; it is not GitHub-enforced branch protection on the current plan.

## One-time setup for a new checkout

Use Python 3, Git, and an authenticated GitHub CLI. Install the project dependencies for local regression tests.

If the checkout has no custom Git hooks to preserve, enable the local direct-push guard:

```sh
git config --local core.hooksPath .githooks
```

The guard blocks pushes, force pushes, and deletions targeting `main`; feature branches remain pushable. It is enabled in the checkout used to establish this process. New clones need this setup themselves. GitHub's web interface, other clones, alternative hook configuration, and explicitly bypassed hooks can still bypass local safeguards.

## Normal change process

1. Start from the latest `main`, then create a `codex/` branch:

   ```sh
   git switch main
   git pull --ff-only origin main
   git switch -c codex/describe-the-change
   ```

2. Implement the requested change. Preserve original design images and existing prompts. Run relevant local tests; the full offline suite is:

   ```sh
   .venv/bin/python -m unittest discover -s tests -v
   node tests/test_google_apps_script.cjs
   ```

3. Commit on the change branch and push it. Open a pull request targeting `main` using GitHub or `gh pr create`. Use the PR template to describe the actual change and validation. Do not send test emails or run delivery workflows without explicit task authorization.
4. Wait for **Automated tests / Offline regression tests** on the pull request. A green test from a previous commit or a push-only run is not enough for the merge helper.
5. If `main` has changed, update your branch, resolve conflicts, push the resulting commit, and wait for its PR tests again. For example, `git fetch origin` followed by `git merge origin/main` on the feature branch preserves the no-force-push workflow.
6. Validate and merge the authorized PR:

   ```sh
   python3 scripts/merge_pr.py NUMBER --check-only
   python3 scripts/merge_pr.py NUMBER
   ```

   Replace `NUMBER` with the PR number. The helper requires an open, non-draft PR from this repository to `main`; the latest pull-request test run for the exact head commit and its named test job must both succeed. It rejects missing, failed, pending, canceled, and skipped tests. It also requires the current `main` to be included and rechecks both refs before merging. The merge command pins the checked head commit so a new PR commit cannot slip past the check.
7. Return to `main` and pull the merged result. Delete the feature branch if it is no longer needed. Do not merge unrelated PRs simply because they have green tests.

## What is and is not enforced

- GitHub runs existing tests automatically for pushes and PRs. This workflow receives no AI or SMTP secrets.
- `AGENTS.md` and the editor rule direct future agents to follow this process.
- The installed pre-push hook blocks local direct pushes to `main`.
- The merge helper checks current CI results and the exact head before performing a squash merge. It never uses `--admin` or enables automatic merging.
- GitHub Free does not enforce these merge requirements for this private repository. The owner can still click Merge directly or use another tool. Use the helper, and do not bypass it when checks fail.
- Another concurrent change to `main` after the final check cannot be atomically blocked by this client-side helper. For platform-enforced protection against every bypass and race, a supported paid plan would be needed; no upgrade or visibility change is part of this setup.

The daily digest continues running from `main` without using merge credentials. No bot is granted permission to merge PRs or write repository contents. Dependabot can propose changes; its PRs use the same test-and-merge process.
