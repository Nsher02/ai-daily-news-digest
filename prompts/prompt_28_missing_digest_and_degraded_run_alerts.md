Detect missed daily digests and repeated degraded editions. Inspect cron-job.org integration, backup schedules, send_window.py, Actions receipts, and failure alerts first. Implement this prompt only when explicitly asked to execute it.

1. MONITORING
   - Check after the existing 10:00 AM America/Chicago send-window cutoff whether today's expected edition has an SMTP-accepted receipt. Handle DST, delayed active runs, empty feeds, failed/skipped jobs, and manual sends according to the existing receipt rules.
   - Detect repeated raw-headline or partial-summary editions using persisted quality metadata and a configurable consecutive-run threshold. Report missing metadata separately from degraded quality.
   - Avoid duplicate alerts and routine status notifications. Notify on a new actionable failure and optionally its recovery, using stable alert identifiers.
   - A GitHub-only monitor cannot guarantee detection when GitHub itself never starts workflows. Prepare an independent-monitor design and document the external trigger, credentials, destination, and approval needed to activate it.
   - Current failure emails depend on the same SMTP transport as the digest. Make that dependency explicit and propose a separately authorized notification channel for transport failures.
   - Prepare code/configuration in an inactive, reviewable state where external setup is required. Do not silently activate a recurring monitor or invent a notification recipient.

2. VERIFY AND DOCUMENT
   - Use mocked clocks, workflow histories, and notification transports to test missing sends, late success, active runs, DST changes, quality streaks, duplicate alerts, and recovery.
   - Document activation steps and monitoring limits. Do not send alerts/test emails, register an external monitor, change sender configuration, commit, or push without separate authorization.
