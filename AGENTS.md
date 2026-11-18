# Repository workflow

- Keep this repository private. Make every change on a `codex/` branch, not `main`.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md): open a pull request, wait for the current PR commit's **Offline regression tests**, and merge only through `python3 scripts/merge_pr.py NUMBER` after they pass. Never bypass a failing or missing check, force-push `main`, or merge unrelated PRs without authorization.
- Install the local direct-push safeguard with `git config --local core.hooksPath .githooks` when no custom hooks would be displaced. It is a local safeguard, not GitHub-enforced branch protection.
- Preserve existing prompts and design images. Do not send test emails or dispatch a delivery workflow unless explicitly requested for the current task.
