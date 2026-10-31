Final step: update the schedule, then commit and push everything to GitHub.

1. Schedule: in .github/workflows/daily-digest.yml, set the schedule to 8:00 AM Central time using GitHub's timezone field (it handles daylight saving automatically):
     schedule:
       - cron: "0 8 * * *"
         timezone: "America/Chicago"
   Keep workflow_dispatch.
2. In config.yaml, set timezone to America/Chicago so the date in the subject matches.
3. .gitignore: make sure it includes .env, .venv/, digest.html and .claude/.
4. prompts/: if digest.py reads any files from prompts/ at runtime, include it in the commit. If not, leave it uncommitted and tell me what's in it.
5. Secret check before committing: search every file that will be committed for my Gemini key (starts with "AIza"), my app password, and any hardcoded email passwords. If anything is found, stop and tell me.
6. Show me git status and the list of files to be committed.
7. Commit with the message "Add AI Daily News Digest (8 AM Central)" and push to the default branch (main).
8. If the GitHub CLI (gh) is installed and logged in, trigger the workflow with `gh workflow run` and watch it until it finishes, then report the result. If gh isn't available, tell me to run it manually from the Actions tab.