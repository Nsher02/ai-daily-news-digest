I'm building a personal daily email digest of CS and AI news. It's a Python script that runs on GitHub Actions every morning.
Pipeline: RSS feeds → keep the last 26 hours → dedupe → LLM picks and summarizes the top stories → HTML email via iCloud SMTP.

Rules:
- Build ONE stage at a time. After each stage, run it, show me the output, and wait for my OK.
- Use the project's existing .venv (Python 3.13) for all installs and runs. Keep requirements.txt up to date.
- Read all keys and settings from environment variables. Load .env locally with python-dotenv. Never hardcode secrets, and never print secret values.
- Keep it simple: one main script, plus config.yaml for sources and settings, plus requirements.txt.
- Don't create the GitHub Actions workflow until I ask.
Confirm, then wait for stage 1.