Establish a pull-request-first change process while keeping the repository free and private.

1. IMPLEMENT
   - Create persistent agent/editor instructions and a contributor guide requiring feature branches, pull requests, and passing checks before merging.
   - Add and install a local guard against direct pushes, force pushes, or deletions of main, preserving existing custom hooks if any.
   - Provide a fail-closed merge helper that checks the latest PR test run and actual regression job for the exact current head, requires current main to be included, rechecks refs, and pins the head when merging. Never use an admin bypass or auto-merge unrelated PRs.
   - Keep GitHub workflow permissions read-only and do not add a bot/PAT with merge permissions. Explain that local safeguards and conventions are not paid-plan server-side enforcement.

2. VERIFY AND DELIVER
   - Test failed/pending/skipped/missing checks, stale commits, changed refs, wrong PRs, and the real pre-push hook with temporary local repositories.
   - Run all existing offline checks; do not send email or dispatch delivery workflows.
   - Use this process for the setup itself: branch, PR, successful current-head tests, checked merge, and sync main. Preserve images, prompts, and account privacy.
