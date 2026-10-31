Fix four problems with the AI Daily News Digest. Run `git pull` first, since I may have edited files on GitHub. Work through the steps in order, show me the results of each, and don't commit until step 6.

1. DIAGNOSE THE AI SUMMARY FAILURE FIRST
   My last manual run on GitHub sent the fallback email ("The AI summary failed today"). Before changing any code, call the LLM directly with the current settings and print the exact error (HTTP status, error type, message). Tell me which it is: 503 overloaded, 429 quota/rate limit, 404 model not found, or an auth/key problem. Then fix the actual cause. For example: if the model name is retired, switch to a current Gemini Flash model (verify it exists; don't guess).

2. MAKE THE LLM STEP RELIABLE AND FAST (fixes the summary failures and the 10-minute hung run)
   A run was cancelled at the 10-minute job limit because a Gemini request hung with no timeout (the openai client's default is 600s). Fix:
   - Set an explicit 60s request timeout on the OpenAI client.
   - Max 3 retries with short exponential backoff.
   - If the primary model still fails, try a lighter Gemini Flash-Lite model once (verify the name exists).
   - If that fails, wait 5 minutes and try the primary model one final time.
   - Only then send the raw-headlines fallback email.
   - Hard cap: the entire LLM step must finish within 10 minutes no matter what.
   - Whenever the LLM step fails, log the exact error (status code and message) so I can see the cause in the Actions log.
   - Add a 30s timeout to the SMTP connection.
   - Set timeout-minutes in the workflow to 20.

3. FIX THE SCHEDULE (the scheduled run never fired this morning)
   - Primary run: cron "53 7 * * *" with timezone "America/Chicago" (off the top of the hour, when GitHub drops or delays runs).
   - Backup run: a second cron "23 8 * * *" with timezone "America/Chicago".
   - Add a first step that skips the rest of the job if a successful run of this workflow already finished today (America/Chicago date). Use the preinstalled gh CLI with GH_TOKEN: ${{ github.token }} and add `permissions: actions: read` (plus contents: read) to the workflow. Manual workflow_dispatch runs must always run and never be skipped.
   - Keep workflow_dispatch.

4. UPGRADE TO THE TOP AI NEWS SOURCES (at least 10 working sources)
   In config.yaml, remove arXiv cs.AI and IEEE Spectrum Computing. Final list:
   - TechCrunch AI: https://techcrunch.com/category/artificial-intelligence/feed/ (15)
   - The Verge AI: https://www.theverge.com/rss/ai-artificial-intelligence/index.xml (10)
   - Ars Technica AI: https://arstechnica.com/ai/feed/ (10)
   - MIT Technology Review AI: https://www.technologyreview.com/topic/artificial-intelligence/feed (10)
   - Wired AI: https://www.wired.com/feed/tag/ai/latest/rss (10)
   - The Decoder: https://the-decoder.com/feed/ (15)
   - OpenAI News: https://openai.com/news/rss.xml (10)
   - Google DeepMind: https://deepmind.google/blog/rss.xml (10)
   - Hugging Face Blog: https://huggingface.co/blog/feed.xml (10)
   - TLDR AI: https://tldr.tech/api/rss/ai (5)
   - Google News – AI: https://news.google.com/rss/search?q=%22artificial+intelligence%22+OR+%22generative+AI%22+OR+LLM&hl=en-US&gl=US&ceid=US:en (20)
   - Google News – Labs: https://news.google.com/rss/search?q=Anthropic+OR+%22Meta+AI%22+OR+xAI+OR+Mistral&hl=en-US&gl=US&ceid=US:en (15)
   - Hacker News (100+ points): https://hnrss.org/frontpage?points=100 (15)
   Fetch each one and show me how many items it returns. If a feed fails or is empty, tell me rather than silently dropping it.
   - TLDR AI may return one item per newsletter issue. If so, pass a longer snippet (about 1500 chars) for that source so the model sees the actual stories.
   - Google News titles end with " - Publisher". Strip that suffix for dedupe and show the publisher as the source.
   Ranking: the email must include at least 10 stories (up to 15) whenever enough items exist. In the LLM prompt, treat a story covered by multiple sources as a strong signal of importance, rank it higher, and list all its sources. Prioritize major model releases, big company and lab news, funding, and policy over minor product updates. Keep the "(title only)" no-made-up-details rule.

5. TEST
   - Simulate a hanging LLM request and prove the fallback email is still built within the time cap.
   - Do a real dry run and show me the top stories with their sources. Confirm it's an AI summary, not the fallback.
   - Send one real test email.

6. COMMIT
   - Update the README (schedule plus backup run, LLM fallback chain and timeouts, the new source list).
   - Save this prompt as prompts/prompt_10_fix_all.md.
   - Scan everything being committed for secrets (my Gemini key, "AIza" followed by a real key, my app password, the app-password pattern, password assignments). If anything is found, stop and tell me.
   - Commit "Fix schedule, LLM reliability and sources" and push to main. Confirm git status is clean and main is up to date with origin/main.
   - Tell me to run the workflow manually from the Actions tab to verify on GitHub.