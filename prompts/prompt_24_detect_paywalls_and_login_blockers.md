Prevent paywalls, login screens, bot challenges, and subscription messages from being treated as article evidence. Inspect fetch_article, enrich_story, and existing tests first. Implement this prompt only when explicitly asked to execute it.

1. EXTRACTION QUALITY
   - Replace the current reliance on a 300-character threshold with conservative checks for article content and access barriers. Consider HTTP status, final redirect location, content type, extraction quality, and clear page-level access-block signals.
   - Do not reject a legitimate article merely because its text discusses subscriptions, logins, or paywalls. A soft-paywall page may contain usable public article text. Never bypass access controls or use personal credentials.
   - When evidence is unavailable, try another existing source for the same story within the current attempt and time budgets, then use original feed titles and snippets for a shorter summary.
   - Record a concise reason such as login_required, paywall, bot_challenge, or insufficient_text. Do not present uncertain heuristics as confirmed access restrictions.
   - Preserve existing URL provenance, image behavior, both LLM passes, deadline supervision, and snapshot compatibility.

2. VERIFY AND DOCUMENT
   - Use offline fixtures covering long login/subscription pages returning HTTP 200, redirects, 401/403 responses, bot challenges, genuine articles mentioning paywalls, public excerpts, and alternate-source success.
   - Update README and run relevant checks. Do not call Gemini, send email, change SMTP configuration, commit, or push without separate authorization.
