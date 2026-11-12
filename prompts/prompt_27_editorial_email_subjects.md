Improve email subjects so they read like a concise editorial overview of the day's major topics, following the user's Apple News examples. Inspect build_subject, both LLM passes, parsing, checkpoints, and replay first. Implement this prompt only when explicitly asked to execute it.

1. SUBJECT GENERATION
   - Request a subject in the existing final summarization call using only the selected stories' original feed evidence and fetched article text. Add no separate model request.
   - Use two or three short, specific topic phrases, natural sentence casing, and an 'and more' ending when additional stories exist. Aim for roughly 70-110 characters. Preserve proper nouns and avoid hype, unsupported claims, dates, and the digest-name prefix in normal subjects.
   - Example style: 'A new open model, the debate over AI safety rules, and more'. Examples are style guidance, not facts to include in real editions.
   - Validate the subject as a nonempty single-line string with a reasonable hard length limit. Use the existing deterministic build_subject fallback for missing/invalid output, pass-2 failure, old snapshots, and raw-headline editions.
   - Tie an AI-written subject to the complete selected edition. Preserve grounded headlines/summaries and make partial-result behavior explicit.
   - Store/replay the subject consistently and show it in dry-run output so it can be reviewed without sending email.

2. VERIFY AND DOCUMENT
   - Test malformed/missing/overlong subjects, control characters, partial rewrites, fallback editions, old snapshots, and end-to-end mocked subject selection.
   - Update README and run relevant checks. Do not call Gemini, send email, change sender settings, commit, or push without separate authorization.
