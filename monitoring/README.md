# Google Apps Script missing-digest monitor

This monitor uses your Google account to check the private GitHub repository independently of GitHub Actions. It runs free within Apps Script consumer quotas. It checks SMTP acceptance, using the same receipt name and early-manual-run exclusion as send_window.py. It does not inspect the recipient inbox.

## Remove the former reader and keep the monitor

**Keep this monitor if you want an independent missing-digest alert.** It checks GitHub outside GitHub Actions and can report a missing SMTP-acceptance receipt or failed verification even when the digest workflow never starts. It does not read your inbox, prove inbox delivery, improve AI summaries, or resend a digest. Its own Google execution and alert-email delivery can also fail. On a healthy day it is quiet; the first eligible hourly run after 10:20 AM America/Chicago checks that day's receipt and records the result.

The reader and Safari test code have been removed from the repository. Historical prompts and design images remain. **Repository changes do not remove live Google deployments.** To remove all web hosting while keeping the existing hourly monitor:

1. Open the existing Apps Script project and choose **Deploy > Manage deployments**. Archive **every web-app deployment**, including the original reader, blank Safari test, and any other reader tests. Do this **before restoring the standalone monitor's public function names**. Removing source files alone does not stop versioned deployments; archived code versions can still exist in project history.
2. Replace **all of Code.gs** with [google_apps_script.gs](google_apps_script.gs). Do not add a second copy of the monitor. This restores the standalone `checkDigest` and `inspectDigest` entry points without changing the monitor's receipt, deadline, daily state, or alert logic.
3. Delete only the old reader files from the live editor: **Reader.gs**, **Index.html**, and **SafariTest.html**, if present. Remove an extra **Monitor.gs** only if it was an additional copy of the shared monitor now replaced by Code.gs. Remove temporary reader-debug functions such as `inspectReaderIdentity()` if they were placed in another file. Keep Code.gs.
4. Replace **appsscript.json** with [the monitor-only manifest](appsscript.json). It has no web-app configuration and removes the reader's account-email permission. Keep external requests and sending email, which the monitor needs. Save.
5. In **Triggers**, keep exactly one monitor trigger. If its function is `checkDigest_`, change it to **checkDigest**; if it already uses checkDigest, keep it. Preserve **Time-driven > Hour timer > Every hour**, its owning account, and the existing failure-notification settings. Do not add a second trigger or run checkDigest manually.
6. Keep **GITHUB_TOKEN**, **ALERT_EMAIL**, **LAST_CHECK_DATE**, and **LAST_CHECK_STATUS** unchanged. **OWNER_EMAIL** was reader-only and can be removed. Do not revoke the read-only GitHub token while keeping this monitor.
7. Run **inspectDigest** for a read-only check. It sends no email and does not change daily state. At the next normal hourly execution, check that checkDigest completes successfully. Do not reset the daily state to force an extra check.
8. Rename the project **AI Daily News Digest Monitor**, if desired, and remove old reader/test bookmarks. No redeployment is needed for the monitor. Keep editor access private.

The GitHub delivery workflow, cron-job.org scheduler, Gemini/Groq keys, and iCloud SMTP credentials remain unchanged. Do not disable or revoke those services when removing the website.

If you instead delete the entire Apps Script project, first archive its deployments and delete its hourly trigger, then move the project to trash. You will lose the independent monitor, but GitHub Actions still sends the digest. Revoke only the monitor's dedicated, otherwise-unused read-only GitHub token; keep the separate cron-job.org scheduler token. Recreating monitoring later requires reinstalling its source, properties, permissions, and hourly trigger.

## Update an existing installation

These steps apply to monitor-only projects. If removing a former shared reader, complete the removal steps above first.

Repository pushes do not update your Google project automatically. In Apps Script, open **Project Settings**, enable **Show appsscript.json manifest file in editor**, then return to the editor. Replace **appsscript.json** with [the manifest in this folder](appsscript.json) and save. Preserve your existing Code.gs, Script properties, and trigger.

The explicit permissions allow external HTTP requests and sending email. They do not request permission to read your inbox or Drive files. Review **Overview > Project OAuth Scopes** to confirm only those two permissions. Run **inspectDigest** for a read-only check; this does not send a test email. If Google requests renewed consent, review the permissions yourself before approving.

Open **Triggers**, edit the existing **checkDigest** trigger, set **Failure notification settings** to **Notify me immediately**, and save. Do not create a second trigger.

## Set up

1. Open https://script.google.com/ and select **New project**. Name it **AI Daily News Digest Monitor**.
2. Replace the default Code.gs contents with the complete contents of **google_apps_script.gs** in this folder and save. Apply **appsscript.json** using the manifest steps above before authorization.
3. On GitHub, open your personal **Settings > Developer settings > Personal access tokens > Fine-grained tokens**. Generate a token restricted to **Nsher02/ai-daily-news-digest** with **Actions: Read-only**. Set an expiration and a reminder to renew it. Keep the token private.
4. In Apps Script, open **Project Settings > Script properties**. Add **GITHUB_TOKEN** with the token value and **ALERT_EMAIL** with your regular iCloud inbox. Keep the Apps Script project private because project editors can access its properties.
5. Select **inspectDigest** in the editor's function dropdown and click **Run**. Authorize GitHub HTTP requests. Check the execution log for `smtp_accepted` or `missing_digest`. This function sends no email and changes no monitoring state. A successful result only confirms the workflow's SMTP receipt.
6. Open **Triggers** (clock icon), select **Add Trigger**, choose **checkDigest**, **Time-driven**, **Hour timer**, then **Every hour**. Authorize sending email from your Google account when prompted. Set trigger failure notifications to immediate so script execution errors are reported by Google.
7. The first eligible execution each day after **10:20 AM America/Chicago** checks the receipt. With an hourly trigger, the check normally occurs at the first hourly execution after that cutoff, with possible Google scheduling delays. A missing receipt or unavailable GitHub API generates one alert to ALERT_EMAIL. A healthy day is quiet. The script records the daily result in LAST_CHECK_DATE and LAST_CHECK_STATUS. It attempts again if sending the alert fails.

Installing the trigger activates real future alert emails. Do not run checkDigest manually after the cutoff unless you intend to allow a real alert. No additional deployment, web app, purchased domain, SMTP configuration, or cron-job.org job is required.

## Limits and maintenance

- renew the read-only GitHub token before it expires;
- monitor execution errors in Apps Script's Executions screen and Google's trigger-failure emails;
- the monitor itself depends on Google executing the trigger;
- after a missing or unverified result, one alert is sent that day, with no automatic recovery notification;
- inspectDigest can be run at any time for a read-only status check;
- the prepared degraded-summary monitor remains separate, this script covers missing or unverified daily delivery only;
- to stop monitoring, delete the checkDigest trigger from the Triggers screen.

## Monthly maintenance

- In **Project Settings > Script properties**, check that **LAST_CHECK_DATE** is today after the Chicago deadline and **LAST_CHECK_STATUS** is `smtp_accepted`. A stale date needs investigation even if no alert arrived. Never share or screenshot the token value.
- Check **Executions** for failures and confirm the existing trigger still runs every hour with immediate failure notifications.
- Put a reminder in your existing calendar before the GitHub token expiration. Renew with the same single-repository **Actions: Read-only** access, update **GITHUB_TOKEN**, and run **inspectDigest**. Revoke the replaced token after successful verification. No test email is necessary.
- Keep the project private. Only script code, this guide, and the permissions manifest belong in the repository; tokens and recipient values stay in Script properties.

The repository backup does not include live Google properties or triggers. Restoring the project requires the setup steps above. Google failure notifications also depend on Google functioning and cannot guarantee detection of a Google outage.

## Offline verification

From the repository root, run `node tests/test_google_apps_script.cjs` for mocked receipt, alert, deduplication, deadline, authorization failure, and failed-send checks. These checks never call GitHub or send email.
