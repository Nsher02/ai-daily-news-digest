Redesign the digest email and make the summaries longer. Show me each step's results, and don't commit until the end.

1. DESIGN
   Match the layout and style of the Apple News email screenshot(s) in design/ (reference.png etc.): typography hierarchy, spacing, publisher name placement above headlines, image placement, section headers, overall feel.
   - Do NOT use Apple logos, the "Apple News" name or any Apple branding. Keep the "AI Daily News Digest" title.
   - Email-safe HTML: table-based layout with inline CSS, a system font stack (-apple-system, etc.), mobile-first, and it must look good in iCloud Mail on iPhone in both light and dark mode.
   - Images: use the article's image when available (feed media/enclosure, or the article's og:image). Skip the image cleanly when there isn't one. Never show broken image boxes.

2. PARAGRAPH-LENGTH SUMMARIES (two-pass)
   - Pass 1 (unchanged): the LLM picks the top 10–15 stories from all the feed items.
   - Then fetch each selected story's article page (parallel, 10s timeout each) and extract the main article text (use a library like trafilatura). Trim each to about 4,000 characters.
   - Google News links are redirect URLs: resolve them to the real publisher URL if possible. If not, use a direct link from another source that covered the same story.
   - Pass 2: ONE batched LLM request that writes a 4–6 sentence paragraph per story: what happened, key details and numbers, and why it matters. Use ONLY facts in the fetched article text and snippets. Never invent details.
   - If an article can't be fetched (paywall, error), write a shorter summary from the snippet only, and never pad it with guesses.
   - Keep the existing fallback chain, timeouts and the 10-minute LLM cap. Normal runs should use at most 3 Gemini requests.

3. TEST
   - Dry run, then open digest.html and show me a screenshot of the result next to design/reference.png so I can compare.
   - Show me 3 sample summaries alongside the source article URLs so I can check they're accurate.
   - Send one real test email.

4. COMMIT
   - Update the README. Save this prompt as prompts/prompt_11_redesign.md. Commit design/ too.
   - Run the secret scan, commit "Apple News-style layout and paragraph summaries", push to main, and confirm git status is clean.
