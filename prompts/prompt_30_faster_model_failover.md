Reach the backup model sooner when the main AI model is unavailable. Inspect run_llm_chain and the shared stage deadline before implementation.

1. RETRY TIMING
   - Try the backup immediately after the initial primary attempt fails or returns an incomplete selection.
   - Reduce primary retries to one and the final cooldown to 15 seconds. Keep per-request timeouts and the overall stage deadline enforced.
   - Preserve permanent-error skipping, partial results, grounding, and delivery behavior.

2. VERIFY AND PUBLISH
   - Use mocked model responses and a simulated clock to verify immediate backup, exhaustion timing, and deadline bounds. Run the full offline regression suite.
   - Update README configuration and retry documentation; preserve images and earlier prompts. Commit and push, then verify automatic tests on GitHub. Do not send a test email or call live AI services.
