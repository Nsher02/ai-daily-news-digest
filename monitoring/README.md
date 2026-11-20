# Google Apps Script missing-digest monitor

This monitor uses your Google account to check the private GitHub repository independently of GitHub Actions. It runs free within Apps Script consumer quotas. It checks SMTP acceptance, using the same receipt name and early-manual-run exclusion as send_window.py. It does not inspect the recipient inbox.

## Shared monitor and reader project

If you have added the private reader to this project, use the combined manifest in [reader/appsscript.json](../reader/appsscript.json), not the monitor-only manifest here. Preserve Reader.gs, Index.html, OWNER_EMAIL, the existing monitor code/properties, and the hourly checkDigest trigger. See [the combined setup guide](../reader/README.md).

## Update an existing installation

These steps apply to monitor-only projects. For a shared reader project, use the combined guide above.

Repository pushes do not update your Google project automatically. In Apps Script, open **Project Settings**, enable **Show appsscript.json manifest file in editor**, then return to the editor. Replace **appsscript.json** with [the manifest in this folder](appsscript.json) and save. Preserve your existing Code.gs, Script properties, and trigger.

The explicit permissions allow external HTTP requests and sending email. They do not request permission to read your inbox or Drive files. Review **Overview > Project OAuth Scopes** to confirm only those two permissions. Run **inspectDigest** for a read-only check; this does not send a test email. If Google requests renewed consent, review the permissions yourself before approving.

Open **Triggers**, edit the existing **checkDigest** trigger, set **Failure notification settings** to **Notify me immediately**, and save. Do not create a second trigger.

## Set up

1. Open https://script.google.com/ and select **New project**. Name it **AI Daily News Digest Monitor**.
2. Replace the default Code.gs contents with the complete contents of **google_apps_script.gs** in this folder and save. Apply **appsscript.json** using the manifest steps above before authorization.
3. On GitHub, open your personal **Settings > Developer settings > Personal access tokens > Fine-grained tokens**. Generate a token restricted to **Nsher02/ai-daily-news-digest** with **Actions: Read-only**. Set an expiration and a reminder to renew it. Keep the token private.
4. In Apps Script, open **Project Settings > Script properties**. Add **GITHUB_TOKEN** with the token value and **ALERT_EMAIL** with your regular iCloud inbox. Keep the Apps Script project private because project editors can access its properties.
5. Select **inspectDigest** in the editor's function dropdown and click **Run**. Authorize GitHub HTTP requests. Check the execution log for `smtp_accepted` or `missing_digest`. This function sends no email and changes no monitoring state. A successful result only confirms the workflow's SMTP receipt.
6. Open **Triggers** (clock icon), select **Add Trigger**, choose **checkDigest**, **Time-driven**, **Minutes timer**, then **Every 15 minutes**. Authorize sending email from your Google account when prompted. Set trigger failure notifications to immediate so script execution errors are reported by Google.
7. The first eligible execution each day after **10:20 AM America/Chicago** checks the receipt. Normally this means a check around 10:20–10:35, with possible scheduling delays. A missing receipt or unavailable GitHub API generates one alert to ALERT_EMAIL. A healthy day is quiet. The script records the daily result in LAST_CHECK_DATE and LAST_CHECK_STATUS. It attempts again if sending the alert fails.

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
- Check **Executions** for failures and confirm the existing trigger still runs every 15 minutes with immediate failure notifications.
- Put a reminder in your existing calendar before the GitHub token expiration. Renew with the same single-repository **Actions: Read-only** access, update **GITHUB_TOKEN**, and run **inspectDigest**. Revoke the replaced token after successful verification. No test email is necessary.
- Keep the project private. Only script code, this guide, and the permissions manifest belong in the repository; tokens and recipient values stay in Script properties.

The repository backup does not include live Google properties or triggers. Restoring the project requires the setup steps above. Google failure notifications also depend on Google functioning and cannot guarantee detection of a Google outage.

## Offline verification

From the repository root, run `node tests/test_google_apps_script.cjs` for mocked receipt, alert, deduplication, deadline, authorization failure, and failed-send checks. These checks never call GitHub or send email.
