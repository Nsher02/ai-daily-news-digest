GitHub's built-in cron is unreliable, so add an external trigger as the main schedule.

1. In the workflow, add a workflow_dispatch input "trigger" (default "manual"). The external scheduler will send trigger=external-schedule.
   - Apply the send-window + "already sent today" check to runs with event=schedule AND to workflow_dispatch runs with trigger=external-schedule.
   - Plain manual runs (trigger=manual) always send.
   - Keep the GitHub cron as a backup. The check guarantees only one email per day.
   - Add tests for: external trigger at 7:50 (sends), GitHub cron after that (skips), external trigger outside the window (skips), manual run (always sends).

2. Give me step-by-step instructions for:
   a) Creating a fine-grained GitHub token: only this repository, only "Actions: Read and write", 1-year expiration. Include a reminder to add a calendar event before it expires, since the trigger stops working when it does.
   b) Setting up cron-job.org: daily at 7:50 AM, time zone America/Chicago. Give the exact URL (the workflow dispatches endpoint for this repo and workflow file), method POST, all required headers (Accept, Authorization: Bearer <token>, X-GitHub-Api-Version, Content-Type) and the JSON body {"ref":"main","inputs":{"trigger":"external-schedule"}}. Also turn on its failure notifications.
   c) Testing it: use cron-job.org's test-run button, then confirm with gh that a workflow_dispatch run with trigger=external-schedule appeared. Since it's outside the morning window, it should skip without emailing.

3. Never put the token in the repo, the README or .env. It only lives in cron-job.org.

4. Update the README, save this prompt as prompts/prompt_14_external_trigger.md, run the secret scan, commit "Add external scheduler trigger" and push to main.