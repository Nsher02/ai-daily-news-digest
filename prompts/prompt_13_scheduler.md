The scheduled digest has NEVER run: no runs with event=schedule exist in Actions on Oct 31 or Nov 1. Manual runs work. Fix the scheduling.

1. CHECK FOR BLOCKERS (use gh)
   - Confirm the workflow is active: gh api repos/{owner}/{repo}/actions/workflows (state must be "active").
   - Confirm Actions are enabled for the repo, main is the default branch, and the workflow file on main has a valid `on: schedule` block.
   - List all runs for this workflow with their event types to confirm none were scheduled.
   Report what you find before changing anything.

2. STOP DEPENDING ON THE CRON `timezone` FIELD
   - Remove `timezone:` and use plain UTC crons: "53 12,13,14 * * *" and "23 12,13,14 * * *".
   - Add a first step "Check send window" for scheduled runs only: continue only if the current America/Chicago time is between 7:45 and 10:00 AM AND no scheduled email has been sent yet today (Chicago date). Otherwise log the reason and stop. The send goes out at about 7:53 AM Chicago, with retries during the morning, and DST is handled automatically in both CST and CDT.
   - Count only runs that actually sent an email (scheduled or manual) as "sent today", EXCEPT manual runs before 7:45 AM Chicago, which must not block the morning email.
   - Manual runs (workflow_dispatch) always send, regardless of the window.
   - Add unit tests for the window logic: CST and CDT dates, the DST switch days, a 6:53 run (skip), 7:53 (send), 8:23 after a send (skip), and an early manual run (doesn't block).

3. NEVER FAIL SILENTLY
   Add a final workflow step with `if: failure()` that emails me "AI Daily News Digest failed – check GitHub Actions" using the same SMTP secrets.

4. PROVE THE SCHEDULER FIRES (don't skip this)
   - Add a temporary test cron about 10 minutes from now (UTC), which only logs "TEST: scheduler fired" and exits without sending an email.
   - Commit and push. Then poll with gh every few minutes for up to 45 minutes until a run with event=schedule appears. Show it to me.
   - If one appears: remove the test cron, commit and push.
   - If NONE appears within 45 minutes: tell me, and set up plan B. An external free scheduler (like cron-job.org) triggers the workflow every morning through GitHub's workflow_dispatch API. Give me step-by-step instructions to create a fine-grained GitHub token limited to ONLY this repo with only "Actions: read and write" permission, and the exact URL, method, headers and body to enter in the scheduler. Make the send-window check also apply to these API-triggered runs.

5. COMMIT
   Update the README. Save this prompt as prompts/prompt_13_scheduler.md. Run the secret scan, commit "Make scheduled delivery reliable" and push to main. Tell me in 3–4 lines what was wrong, what changed, and what I'll see in Actions tomorrow morning.