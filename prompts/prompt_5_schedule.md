Stage 5: Create .github/workflows/daily-digest.yml:
- name: "AI Daily News Digest"
- triggers: schedule cron "7 14 * * *" (7:07 AM Arizona, which is UTC-7 with no daylight saving) and workflow_dispatch for manual runs
- runs-on ubuntu-latest, timeout-minutes 10
- current major versions of actions/checkout and actions/setup-python, Python 3.13, pip cache
- install requirements.txt, then run the script for real (not --dry-run)
- pass these secrets as env vars: LLM_API_KEY, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO, EMAIL_FROM
  EMAIL_FROM is my iCloud alias for the digest (already in .env and GitHub Secrets). Send FROM that address with the display name "AI News", while still logging in with SMTP_USER. Fall back to SMTP_USER only if EMAIL_FROM is empty.

Confirm the title changes are in place (in config.yaml, not hardcoded):
- Subject: "AI Daily News Digest — <Weekday, Month Day>" (Phoenix time)
- Heading at the top of the email body: "AI Daily News Digest"
- From display name: "AI News"; To display name: "Noah Sher"

Also:
- Make sure the script exits with a non-zero code if sending the email fails, so the GitHub run shows red.
- Check that .gitignore covers .env, .venv and digest.html.
- Send one real test email locally so I can confirm the From line shows "AI News".
- Then show me the workflow file and the output of git status. Don't commit yet.