Prevent repeated stories across daily digest editions. Inspect the current pipeline, tests, send window, and receipt behavior first. Implement this prompt only when explicitly asked to execute it.

1. HISTORY AND SELECTION
   - Persist a bounded history of stories actually accepted for email delivery across GitHub Actions runners. Include normalized original/resolved URLs, source evidence, titles, and the edition date. Propose and document the simplest durable storage compatible with the repository's permissions and existing concurrency.
   - Prefer fresh stories over recently emailed coverage. Handle different publisher coverage of one event conservatively, retaining genuinely new developments. Do not use broad keyword matches to suppress unrelated stories.
   - Make the history horizon configurable. Do not pad a quiet day's digest with old stories to meet the minimum. Apply the policy consistently to AI and raw-headline fallback editions.
   - Update history only after SMTP acceptance. Dry runs, offline replay, failed sends, and discarded candidates must not advance sent history. Specify how manual sends interact with history while preserving their ability to send.
   - Use atomic writes, bounded retention, and explicit handling of missing, corrupt, stale, or failed history restoration. Explain the unavoidable gap between SMTP acceptance and durable state publication.

2. VERIFY AND DOCUMENT
   - Add focused offline tests for overlapping 26-hour windows, syndicated links, meaningful updates, quiet days, unsuccessful sends, manual sends, and history failures.
   - Update README with storage, retention, recovery behavior, and any permissions required. Keep the existing sender configuration and email design.
   - Run relevant checks and summarize the result. Do not call Gemini, send email, commit, push, or activate external services without separate authorization.
