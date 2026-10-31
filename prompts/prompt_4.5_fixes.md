Two fixes before the real send:

1. I'm renaming SMTP_USERNAME to SMTP_USER in .env to match my GitHub Secret. Remove the SMTP_USERNAME fallback.

2. Fix the hallucinated details in the summaries:
- In the LLM prompt, mark items that have no snippet as "(title only)".
- Add this rule: for title-only items, summarize ONLY what the headline itself says (e.g. "HN discussion of …" / "Post about …"). Never add details, causes, numbers or quotes that aren't in the item's title or snippet. If unsure, keep it short and say less.
- Lower temperature to 0.2.

Then do a dry run and show me the Hacker News summaries so I can check them against the titles. Don't send the real email yet.