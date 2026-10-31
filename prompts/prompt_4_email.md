Stage 4: Render the digest as a clean, mobile-friendly HTML email (inline CSS) with a plain-text fallback.
Subject: "CS & AI Digest — <weekday, month day>" in America/Phoenix time.
Send via SMTP using SMTP_HOST, SMTP_PORT (587 with STARTTLS), SMTP_USER, SMTP_PASSWORD and EMAIL_TO.
Add a --dry-run flag that saves digest.html instead of sending (and add digest.html to .gitignore).
If the LLM step fails, still send the raw headlines grouped by source with a note saying the summary failed.
If there are no items at all, send nothing.