Fix full-size Groq paragraph rewriting and preserve normal summary length within the free plan.

1. IMPLEMENT
   - Replace the single 15-story Groq rewrite with batches of at most three, retaining full configured evidence when the request fits. Restore original story IDs and retry only missing/short results.
   - Keep editorial instructions, grounding, coverage validation, and paragraph-length requirements identical for Gemini and Groq; only transport, batching, and rate pacing differ.
   - Target grounded 4–6 sentence paragraphs around 90–160 words for sufficiently rich articles. Keep sparse-source summaries shorter; never pad missing facts. Reject truncated output and validate coverage.
   - Estimate input tokens, reserve completion tokens, and pace a shared rolling token budget below the free limit. Bound per-run usage and all waits by a supervised deadline, allowing time for pacing. Never change billing plans.
   - Checkpoint each completed batch and preserve an edition-wide subject/TLDR. Save combined replay responses with correct story numbering.

2. VERIFY AND PUBLISH
   - Test full 15-story coverage, paragraphs, partial/malformed/truncated replies, missing-only retries, original numbering, source retention, rate pacing, deadlines and checkpoint preservation.
   - Run all offline tests. Provide and run live 15-story verification using fictional evidence, without SMTP credentials or email sending.
   - Update README and configuration documentation. Preserve prompts/images, commit and push, verify automatic tests, and report measured live results and remaining limits honestly.
