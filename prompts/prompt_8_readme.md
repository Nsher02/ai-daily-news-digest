Rewrite README.md so it fully documents this project. Future me should be able to understand and edit it without any other notes. Read the actual code, config.yaml, requirements.txt and the workflow file, and document what's really there. Don't guess, and don't copy details from this prompt if the code differs.

Include these sections:

1. Overview: what the project does in 2-3 sentences (a daily AI/CS news email digest sent to my iCloud inbox, built with Python and GitHub Actions).

2. How it works: the pipeline step by step (fetch RSS feeds → keep the last N hours → dedupe → Gemini picks and summarizes the top stories → HTML email via iCloud SMTP). Explain the ID-mapping design (the LLM returns item IDs and links are attached in code, so it can't invent URLs), the "(title only)" anti-hallucination rule, the raw-headlines fallback when the LLM fails, retries, and the no-items behavior.

3. Project files: a short table of each file/folder and its purpose (digest.py, config.yaml, requirements.txt, .github/workflows/daily-digest.yml, prompts/, .claude/, .gitignore, digest.html).

4. Schedule: when it runs (8:00 AM America/Chicago using GitHub's cron timezone field, which handles daylight saving), how to change the time or time zone, that runs can start late, and how to trigger a manual run (Actions → AI Daily News Digest → Run workflow).

5. Configuration (how to edit): every setting in config.yaml and what it controls. Include exact examples for:
   - adding or removing a news source
   - changing the number of stories, the sections, or the lookback window
   - changing the subject prefix, the From name or the To name
   - switching the LLM model or provider (LLM_MODEL / LLM_BASE_URL, OpenAI-compatible endpoint)

6. Secrets: a table of the 7 GitHub Secrets (LLM_API_KEY, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_TO, EMAIL_FROM): what each is, where it comes from (Google AI Studio, account.apple.com app-specific password, iCloud alias), and how to update one. Note that GitHub Secrets can't be viewed after saving, so keep copies in a password manager. NO real values. Use placeholders only.

7. Running locally (optional): clone, create .venv, install requirements, create a .env from a placeholder template (show all 7 variable names with fake values), run with --dry-run, then for real. Remind me never to commit .env.

8. Maintenance and troubleshooting:
   - a red Actions run: where to find the error, plus the most common causes (misnamed secret, expired app password, Gemini 503/rate limit, a broken feed)
   - changing my Apple password revokes all app-specific passwords, so generate a new one and update SMTP_PASSWORD
   - rotating the Gemini key
   - the iCloud alias: EMAIL_FROM, its display name, and the Send From setting
   - if the repo is ever made public, scheduled workflows are disabled after 60 days of no activity
   - cost: Gemini free tier, GitHub Actions minutes

Keep it clear and skimmable: headings, short paragraphs, tables and code blocks where they help.

Also save this exact prompt as prompts/prompt_8_readme.md.

Before committing, scan README.md and prompts/prompt_8_readme.md for my Gemini key, the "AIza" prefix followed by a real key, my app password, the app-password pattern, and password assignments. If anything is found, stop and tell me.

Then commit both files with the message "Document project in README" and push to main. Confirm git status shows "working tree clean" and that main is up to date with origin/main.