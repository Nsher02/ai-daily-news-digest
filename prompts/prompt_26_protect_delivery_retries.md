Reduce duplicate digest emails during retries and runner failures while keeping the current sender configuration. Inspect concurrency, send windows, delivery records, and SMTP receipts first. Implement this prompt only when explicitly asked to execute it.

1. CONSISTENT EDITIONS AND RETRIES
   - Persist the fully prepared edition before delivery, including its date, recipient identity, subject, text/HTML content, and stable edition/message identifiers. Reuse that edition on retry rather than generating different content.
   - Keep delivery records consistent with cross-day history and existing scheduled-run serialization. Define separate identifiers for deliberate manual sends so tests or manual editions do not accidentally suppress the scheduled edition.
   - Design safe recovery for crashes before send, during SMTP exchange, after acceptance, and before durable receipt publication. Expose ambiguous acceptance explicitly and document the tradeoff between duplicate risk and missed delivery.
   - Do not claim exactly-once delivery from SMTP, a Message-ID, or GitHub receipts. A Message-ID alone does not guarantee provider deduplication.
   - Document how a future provider idempotency key could protect retries of the exact same persisted request, including retention limits and payload mismatch handling. Defer provider-specific headers and API changes until the sender migration is authorized.

2. VERIFY AND DOCUMENT
   - Add offline failure-injection tests covering each crash boundary, repeated scheduled triggers, manual sends, corrupted prepared editions, and rejected sends.
   - Document storage, access, cleanup, recovery, and remaining SMTP limitations. Do not change email providers, send email, call Gemini, commit, or push without separate authorization.
