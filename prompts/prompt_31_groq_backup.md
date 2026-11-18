Add Groq as an optional independent free-tier backup to Gemini.

1. IMPLEMENT
   - Use a separate GROQ_API_KEY and Groq endpoint with a current free-tier production model. Keep Gemini primary and Lite first, and preserve Gemini-only behavior when the key is absent.
   - Bound requests and cooldowns by the existing deadline. Limit prompt size while preserving original item IDs, evidence-based summaries, and link validation. Do not silently upgrade billing.
   - Document secure key setup in GitHub, model override, free limits, and delivery caveats.

2. VERIFY AND PUBLISH
   - Mock independent clients, provider failures, absent credentials, and successful fallback; run all regressions.
   - Provide a manual live verification using synthetic sources and forced Gemini failure for both AI stages. Send one clearly labeled test email only after a complete live Groq result. Do not modify daily receipt/history state during verification.
   - Update README, preserve all prompts and images, commit and push. Verify automatic GitHub tests. Guide the user through account/key steps without requesting the key in chat.
