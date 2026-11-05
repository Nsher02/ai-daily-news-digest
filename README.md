# ai-daily-news-digest

A personal daily email digest of AI news, delivered to an iCloud inbox every morning. A single Python script pulls 13 RSS feeds, asks Google Gemini to pick the most important stories, reads each story's full article, has Gemini write a paragraph-length summary of each, and sends a news-app-style HTML email (with article images, light and dark mode) through iCloud SMTP. GitHub Actions runs it every morning, triggered by cron-job.org with GitHub's own cron as a backup, so nothing needs to stay running on your machine.

---

## How it works

Everything lives in `digest.py`; `main()` runs these steps in order.

| # | Step | Function | What happens |
| --- | --- | --- | --- |
| 1 | Fetch | `fetch_all` / `fetch_feed` | Downloads each feed in `config.yaml` with `requests` (timeout `request_timeout`, browser-like `user_agent`) and parses it with `feedparser`. Google News titles lose their ` - Publisher` suffix and the publisher becomes the source; TLDR AI issues are expanded into individual article items (`fetch_issue_stories`), each with its own headline, snippet and destination link. |
| 2 | Filter | `fetch_feed` | Keeps items published in the last `lookback_hours`. Items with no date are dropped (logged as a warning). Each feed is sorted newest first and capped at its `max_items`. |
| 3 | Dedupe | `dedupe` | Groups items matching a **normalized URL** or **normalized title** into one candidate, retaining every source link and the best snippet per publisher. |
| 4 | Pass 1: pick | `summarize` / `run_llm_chain` | Sends all items to Gemini in one request. The model picks `min_stories`–`max_stories` stories (10–15), merges duplicates, ranks multi-source stories higher, sorts them into sections, and returns JSON with short summaries. |
| 5 | Read articles | `enrich_story` | For each picked story, in parallel (10 workers): resolves Google News redirect links to the publisher's URL (`decode_google_news`), fetches the article page (`article_timeout`, 10s) and extracts the main text with **trafilatura**, trimmed to `article_chars` (4,000). Also picks the story's image (see [Email design](#email-design)). |
| 6 | Pass 2: write | `build_summary_prompt` / `run_llm_chain` | **One** batched Gemini request writes a 4–6 sentence paragraph per story (what happened, key details and numbers, why it matters) using only the fetched article text and feed snippets. Stories whose article couldn't be fetched get 1–3 sentences from the snippets only. |
| 7 | Render | `render_html` / `render_text` | Builds the email-safe HTML (table layout, inline CSS, dark-mode styles) plus a plain-text alternative. |
| 8 | Send | `send_email` | Connects to `SMTP_HOST:SMTP_PORT`, upgrades with STARTTLS, logs in as `SMTP_USER`, sends from `EMAIL_FROM`. |

**Normalization used by dedupe:**
- URL: lowercase scheme and host, strip `www.`, drop `utm_*` query params, the `#fragment` and a trailing `/`. Other query params are kept (so `?id=1` and `?id=2` stay distinct).
- Title: lowercase, curly quotes → straight, punctuation removed, whitespace collapsed.

Grouping includes transitive URL/title matches and preserves original evidence. Distinct publishers are counted once even when also found through Google News. This only catches *exact* duplicates. The same story covered by two outlets with different headlines gets through dedupe, and the LLM merges it in pass 1. The prompt treats a story covered by several sources as a strong signal of importance: it ranks higher and lists every source. It also prioritizes major model releases, big company and lab news, funding and policy over minor product updates.

### The ID-mapping design (why links can't be invented)

Each item goes into the prompt as `[id] (source) title` plus a snippet. The model is told to return only item **IDs**, never URLs:

```json
{"tldr": "...", "excluded_ids": [], "sections": [{"name": "...", "stories": [{"ids": [3, 17], "headline": "...", "summary": "..."}]}]}
```

The code maps each group ID back to its original feed evidence and source links. IDs must be integers in range (booleans are rejected). Repeated IDs within a story are collapsed; stories reusing an already selected ID or normalized headline are skipped. Headlines and summaries must be nonempty strings. Unknown sections are discarded, duplicate section blocks are combined, sections follow the configured editorial order, and the selected digest is capped at `max_stories`. A response with no usable stories fails validation. The raw-headlines emergency fallback retains its existing all-items behavior.

A merged story keeps original source links. Its headline links to the article that pass 2 actually read (falling back to the first direct link), with other publishers shown as "Also covered by …". Publisher names are compared without case, whitespace or punctuation differences; different aliases for the same publisher are not automatically resolved.

### The "(title only)" anti-hallucination rule

Some feeds carry no real description. Hacker News (hnrss) fills the summary with boilerplate like `Article URL: … Comments URL: … Points: 132 # Comments: 72`. `clean_text` strips HTML tags and that boilerplate (`FEED_BOILERPLATE`) and truncates to 300 characters (or the feed's `snippet_chars`; TLDR AI allows up to 1500 characters per extracted story). Google News summaries only repeat the title, so they're dropped. If nothing is left, the item is sent to the model marked **`(title only)`**.

The prompt tells the model to summarize those items using only what the headline says ("HN discussion of …"), and never to add details, causes, numbers or quotes that aren't in the title or snippet. Temperature is `0.2` to keep output conservative.

### Paragraph summaries (pass 2)

After pass 1, `enrich_story` prepares each story:

- **Google News links** (`news.google.com/rss/articles/…`) don't redirect with a plain GET. `decode_google_news` reads the article's signature from Google's page and asks Google's `batchexecute` endpoint for the real URL, the same way the Google News web app does. If that fails, the story uses a direct link from another source that covered it; a Google News link is only used as a last resort.
- **Which article is read:** the first direct link (not Google News, not a TLDR issue page); if it fails or has under 300 characters of text, the next one. At most two tries per story.
- **Paywalls and errors:** the story is marked "article unavailable" and pass 2 writes a shorter summary from the headline and feed snippets only.

Pass 2 sends all stories in **one** request containing original feed titles, snippets and article text. Generated pass-1 headlines are omitted from the evidence. Both prompts tell the model to treat source content as data and ignore embedded instructions. The prompt says to use only facts from that text, never names, numbers, dates, quotes or background from the model's own knowledge, and to leave out "why it matters" rather than guess. The model returns final headlines and summaries plus a final TL;DR. Missing or invalid rewrites keep their pass-1 fields. The final TL;DR replaces the first one only when every story has a valid rewrite. Prompt instructions reduce risk but do not prove factual accuracy.

**Gemini usage:** a normal run makes **2 requests** (pass 1 + pass 2). Pass 2 uses the same retry chain minus the 5-minute final wait, because a pass-1 digest is already a good fallback.

### Failure behavior

| Situation | What happens | Exit code |
| --- | --- | --- |
| One feed fails (timeout, HTTP error, unparseable) | Logged as `ERROR <feed>: failed, skipping`; the run continues with the other feeds. **No retry.** | 0 |
| No items at all after fetch + dedupe | Logs `no items at all; nothing to send` and **sends nothing**. | 0 |
| Gemini error (503, 429, timeout, bad JSON, zero usable stories) | Runs the LLM fallback chain below. If every step fails, the email is sent anyway as a **raw-headlines fallback**: every item grouped by source, under a yellow note saying "The AI summary failed today…". | 0 |
| Pass 2 fails (all attempts) or articles can't be fetched | Logs `paragraph summaries failed, using short summaries`; the email uses pass 1's 1–2 sentence summaries, with resolved links and images. | 0 |
| Sending the email fails (bad login, SMTP down) | Logs `sending email failed: …` and exits non-zero so the GitHub run shows **red**. The SMTP connection has a 30s timeout. | 1 |

**LLM fallback chain** (`run_llm_chain`, used by both passes, all values in `config.yaml`):

1. Primary model (`gemini-3.5-flash`), **60s timeout per request** (`llm_timeout`).
2. Up to **3 retries** of the primary with exponential backoff of 2s, 4s, 8s (`llm_retries`, `llm_backoff`). Errors 400/401/403/404, and a 429 for the **daily** free-tier quota, skip the remaining retries, since retrying the same model won't help.
3. The lighter model (`gemini-3.5-flash-lite`) **once**.
4. Pass 1 only: wait **5 minutes** (`llm_final_wait`), then the primary one last time.
5. Only then: the raw-headlines fallback email (pass 1) or the short pass-1 summaries (pass 2).

The requested minimum is clamped to the available duplicate groups. A shorter selection is accepted immediately when its selected/merged IDs and `excluded_ids` are disjoint and account for every input group. Otherwise the existing retry chain tries for a fuller selection and keeps the short digest as a fallback. Semantic eligibility and merging remain model judgments; Python validates the accounting, not whether every exclusion was editorially justified. Every failed attempt logs the exact cause, for example `ERROR LLM pass 1 attempt 1 (gemini-3.5-flash) failed after 4s: HTTP 503 InternalServerError: [{"error": {"code": 503, "message": "This model is currently experiencing high demand. …"}}]`.

**Hard cap:** the whole LLM step (pass 1, article fetching and pass 2) has a **10-minute** budget (`llm_step_cap: 600`). If the cap hits after pass 1 succeeded, the email uses the pass-1 digest instead of raw headlines. The chain shortens the 5-minute wait if needed so the last attempt fits, and a parent supervisor kills the worker subprocess (including its fetch threads) when the deadline is reached. Atomic checkpoints preserve completed pass-1/enrichment results. A small cleanup reserve is deducted from the configured cap. Enrichment requests use the remaining deadline; up to one request timeout (or half the remaining budget) is reserved for pass 2. At most three image candidates are checked, and optional image work stops near the enrichment cutoff. OS scheduling and process cleanup can add a small amount of overhead; a hung request cannot keep background workers alive indefinitely. Worst case: about 4.5 min of primary attempts, 1 min of Flash-Lite, a wait shortened to about 3.5 min, then 1 min for the final try.

### Email design

The email follows `design/Apple_News_reference.jpeg`: a compact morning briefing with distinct black and gray tones. It retains **AI Daily News Digest** branding and includes no Apple logos or promotional modules.

- **Palette:** charcoal outer canvas `#383838`, near-black reading column `#1c1c1c`, bright headlines `#f5f5f5`, soft gray summaries `#b0b0b0`, muted source names `#a0a0a0`, thin dividers `#484848`, strong rules `#999999`, and pink Top Stories lettering `#ff375f`.
- **Header fade:** the reading column starts at `#2c2c2e`, passes through `#232324`, and fades into `#1c1c1c` over the first 160px, matching the reference. Inline solid backgrounds remain as fallbacks for clients that do not support gradients.
- **Header:** small date, compact sans-serif “Good Morning From AI Daily News Digest” masthead, then a serif TL;DR.
- **Top stories:** text-first bullets with bold serif headlines flowing into gray summaries. There is no large hero image.
- **Other sections:** uppercase section titles, serif headlines with publisher credits below, square thumbnails on the right when available, and full-width gray summaries.
- **Disclosure footer:** a full-width `#2c2c2c` gray band sits below the near-black story area, with muted `#b0b0b0` text, 24px top padding, and the same responsive side insets as the content. This replaces the previous inset rule and dark footer.
- **Readability:** comfortable line heights intentionally avoid the overlapping text visible in the reference. Existing story content, source links, and plain-text email are preserved.

**Email-safe HTML:** presentation tables, a 600px maximum reading column, inline critical colors, `bgcolor` fallbacks, and system fonts. The reference's dark palette is the default in both light and dark system appearances; this replaces the previous adaptive white background. A mobile media query reduces padding, masthead size, and thumbnails. Clients may override colors or fonts, block remote images, or ignore image cropping; browser previews do not guarantee identical rendering in every mail client.

**Offline preview:** run `.venv/bin/python digest.py --replay tests/fixtures/replay.json --output /private/tmp/digest-design-preview.html`. This renders saved content without API calls or sending mail. `digest.html` contains a representative synthetic multi-section design preview, not a live news edition.

**Images:** for each story the first working one of: the feed item's `media:content` / `media:thumbnail` / image enclosure / first `<img>` in its HTML (`feed_image`), then the article's `og:image` (read during the article fetch). Every candidate is checked before use (`image_ok`: https, HTTP 200, `Content-Type: image/*`), and a story with no working image simply has no image block, so the email never shows a broken image box.

---

## Project files

| Path | Purpose |
| --- | --- |
| `digest.py` | The whole pipeline: fetch, filter, dedupe, pass 1, article fetching, pass 2 (with retry/fallback chain and hard cap), render, send. Also holds the LLM prompt, the section list, the primary and lite model defaults and the API base URL. |
| `config.yaml` | Feeds and settings you'll edit most often (see [Configuration](#configuration-how-to-edit)). |
| `requirements.txt` | Pinned dependencies: `feedparser`, `openai`, `python-dotenv`, `PyYAML`, `requests`, `trafilatura` (article text extraction). |
| `design/` | `Apple_News_reference.jpeg`, the current visual reference; `reference.png` is the older reference. Not used at runtime. |
| `.github/workflows/daily-digest.yml` | The GitHub Actions workflow: `workflow_dispatch` trigger input (for cron-job.org), backup UTC crons, send-window check, Python setup, secrets → env vars, runs `python digest.py`, emails you if a run fails. |
| `send_window.py` | Decides whether a scheduled run (GitHub cron or `trigger=external-schedule`) sends: inside 7:45–10:00 AM Chicago and nothing sent yet today. Standard library only. |
| `prompts/` | The step-by-step build prompts used to create this project with Claude Code (`prompt_0_brief.md` … `prompt_11_redesign.md`). History only; nothing reads them at runtime. |
| `.gitignore` | Standard Python template plus `.env`, `.venv` and `.claude/` (local Claude Code settings, not tracked). Keeps secrets and the virtualenv out of git; `__pycache__/` is ignored too. |
| `digest.html` | Output of the last `--dry-run`. It's committed, so a dry run will show it as modified in `git status`. |
| `README.md` | This file. |

---

## Schedule

The digest goes out at about **7:50 AM Chicago time** every morning. GitHub's built-in cron proved unreliable here (one run 4.5 hours late, then several missed firings), so an **external scheduler is the main trigger** and GitHub's cron is only a backup:

| Trigger | When | Run name in Actions |
| --- | --- | --- |
| **cron-job.org** (main) calls GitHub's `workflow_dispatch` API with `trigger=external-schedule` | 7:50 AM America/Chicago | `AI Daily News Digest (external-schedule)` |
| **GitHub cron** (backup), plain UTC: `53 12,13,14 * * *` and `23 12,13,14 * * *` | Six firings, 12:23 to 14:53 UTC. CDT (UTC-5) lands them at 7:23 to 9:53 AM, CST (UTC-6) at 6:23 to 8:53 AM | `AI Daily News Digest (github-cron)` |
| **You**, Actions → Run workflow (trigger `manual`) | Whenever | `AI Daily News Digest (manual)` |

The first step, **Check send window** ([`send_window.py`](send_window.py)), applies to cron runs and `external-schedule` runs and guarantees **at most one scheduled email per day**:

- The current America/Chicago time must be between **7:45 and 10:00 AM**. Otherwise the run logs `Skipping: … outside the 07:45-10:00 Chicago send window` and stops. This is how DST is handled. The workflow doesn't use GitHub's cron `timezone:` field.
- **Nothing may have been sent yet today** (Chicago date). A run counts as sent only if it has a successful `SMTP accepted: YYYY-MM-DD` step for today, and only `send_email` returning successfully produces that step. Scheduled and manual sends both count, **except manual runs started before 7:45 AM**, so an early test run doesn't block the morning email. Empty feeds, dry runs, failed sends and skipped runs never count.
- **Plain manual runs** (trigger `manual`, the default) skip the check and always send.

On a normal day, the 7:50 external run sends and every GitHub cron firing skips. If cron-job.org fails, the first GitHub cron firing inside the window sends instead.

Run and job listings are paginated. If the GitHub API call fails, the step fails instead of risking a duplicate, and the failure alert below fires. Concurrency serializes runs, so a run that starts while another is in progress waits for it, then sees its receipt. The script exposes `sent`, `no_items`, `failed`, or `dry_run` through Actions outputs.

SMTP acceptance does not prove inbox delivery. A runner crash between SMTP acceptance and recording the receipt can still cause a duplicate on the next firing. SMTP offers no atomic transaction with GitHub's run metadata.

**Failure alert:** if any step fails, a final step emails you "AI Daily News Digest failed – check GitHub Actions" with a link to the run, using the same SMTP secrets. If the SMTP secrets themselves are broken, only GitHub's own failure notification reaches you. cron-job.org separately emails you if its call to GitHub fails (for example, an expired token).

### External trigger setup (cron-job.org)

The token lives **only in cron-job.org**. Never put it in the repo, this README or `.env`.

1. **Token:** GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token. Expiration: 1 year. Repository access: **Only select repositories** → `ai-daily-news-digest`. Repository permissions: **Actions: Read and write** (GitHub adds Metadata: Read-only automatically). Nothing else. **Add a calendar reminder a week before it expires**, because the main trigger stops working when it does (the GitHub cron backup keeps running).
2. **Job:** cron-job.org → Create cronjob, daily at **7:50**, time zone **America/Chicago**, with this request:

   ```
   POST https://api.github.com/repos/Nsher02/ai-daily-news-digest/actions/workflows/daily-digest.yml/dispatches
   Accept: application/vnd.github+json
   Authorization: Bearer <token>
   X-GitHub-Api-Version: 2022-11-28
   Content-Type: application/json

   {"ref":"main","inputs":{"trigger":"external-schedule"}}
   ```

   Turn on its notifications for failed executions. GitHub answers a successful dispatch with HTTP 204 (no body).
3. **Test:** use the job's test-run button, then check `gh run list --workflow daily-digest.yml -L 3`. A run named `AI Daily News Digest (external-schedule)` should appear. Outside 7:45–10:00 AM it logs `Skipping: … outside the … send window` and sends nothing.

**To rotate the token:** create a new one the same way, paste it into the cron-job.org job's `Authorization` header, run a test, then delete the old token.

**To change the time or time zone**, edit four places:

1. cron-job.org: the job's time and time zone.
2. `.github/workflows/daily-digest.yml`: the UTC backup crons. Pick hours that cover your target local time in both standard and daylight time.
3. `send_window.py`: `TZ`, `WINDOW_START` and `WINDOW_END`.
4. `config.yaml`: `settings.timezone` (used for the date in the subject and heading, and in the receipt step's name).

**GitHub cron runs can start late.** GitHub queues scheduled runs, and they often start minutes or hours after the cron time, or never. That's why it's only the backup. Scheduled runs only fire from the default branch (`main`).

**Manual run:** GitHub → **Actions** → **AI Daily News Digest** → **Run workflow** → branch `main`, trigger `manual` → **Run workflow**. This sends a real email.

The job runs on `ubuntu-latest` with Python 3.13, caches pip, and has a **20-minute** timeout (`timeout-minutes: 20`), comfortably above the 10-minute LLM cap.

---

## Configuration (how to edit)

### `config.yaml` reference

| Key | Current value | Controls |
| --- | --- | --- |
| `settings.lookback_hours` | `26` | How far back to keep items. 26 rather than 24 gives slack for late runs and odd feed timestamps. |
| `settings.timezone` | `America/Chicago` | Time zone for the date in the subject and email heading. Does **not** control when the workflow runs. |
| `settings.request_timeout` | `20` | Seconds per feed request. |
| `settings.article_timeout` | `10` | Seconds per article page, Google News link decode and image check (pass 2 prep). |
| `settings.article_chars` | `4000` | Article text sent to the LLM per story. |
| `settings.min_stories` | `10` | Minimum stories in the email whenever enough items exist. |
| `settings.max_stories` | `15` | Max stories the LLM is asked to pick. |
| `settings.llm_timeout` | `60` | Seconds per Gemini request (per attempt). |
| `settings.llm_retries` | `3` | Retries of the primary model. |
| `settings.llm_backoff` | `2` | Seconds before the first retry; doubles each time (2, 4, 8). |
| `settings.llm_final_wait` | `300` | Seconds to wait before the last try of the primary model (shortened if needed to fit the cap). |
| `settings.llm_step_cap` | `600` | Hard cap on the whole LLM step (both passes and article fetching), in seconds. |
| `settings.user_agent` | browser UA string | Sent with feed requests; some sites block default Python agents. |
| `email.subject_prefix` | `AI Daily News Digest` | Subject is `<prefix> — <Weekday, Month Day>`. Also the big heading at the top of the email. |
| `email.from_name` | `AI News` | Display name on the From line. |
| `email.to_name` | `Noah Sher` | Display name on the To line. |
| `feeds[]` | 13 feeds | Each has `name` (shown in the email), `url` and `max_items` (cap per run). Optional: `snippet_chars` (snippet length sent to the LLM, default 300), `strip_publisher: true` (Google News: strip ` - Publisher` from titles and show the publisher as the source), `expand_issue: true` (TLDR: create separate story items from its web page). |

Headers are built with `email.utils.formataddr`, so names containing `&` or non-ASCII characters are encoded correctly.

### News sources

| Source | `max_items` | Notes |
| --- | --- | --- |
| TechCrunch AI | 15 | |
| The Verge AI | 10 | |
| Ars Technica AI | 10 | |
| MIT Technology Review AI | 10 | Publishes a few times a week; often 0 items in a given 26h window. |
| Wired AI | 10 | |
| The Decoder | 15 | |
| OpenAI News | 10 | Only has items on days OpenAI posts. |
| Google DeepMind | 10 | Only has items on days DeepMind posts. |
| Hugging Face Blog | 10 | |
| TLDR AI | 5 | Issues are expanded into separate stories with up to 1500 characters each. The five-item cap applies to stories; timestamps come from the issue. Extraction failures log a warning and retain the issue as a fallback. |
| Google News – AI | 20 | Search: "artificial intelligence" OR "generative AI" OR LLM. Publisher shown as the source. |
| Google News – Labs | 15 | Search: Anthropic OR "Meta AI" OR xAI OR Mistral. Publisher shown as the source. |
| Hacker News (100+ points) | 15 | Front-page stories with 100+ points. |

A source with 0 items on a given day is normal (quiet blogs, weekends). A source that **fails** logs `ERROR <name>: failed, skipping`.

### Add or remove a news source

Add an entry under `feeds:` (any RSS or Atom feed works):

```yaml
  - name: The Register
    url: https://www.theregister.com/headlines.atom
    max_items: 10
```

To remove one, delete its three lines. Feed order selects the representative headline for exact duplicate groups; every original source link and the best snippet per publisher remain available. Test a new feed with a dry run (see [Running locally](#running-locally-optional)); a bad URL shows up as `ERROR <name>: failed, skipping`.

### Change the number of stories or the lookback window

```yaml
settings:
  lookback_hours: 48   # e.g. for a less frequent schedule
  max_stories: 10
```

### Change the sections

Sections are **not** in `config.yaml`. They're the `SECTIONS` list near the top of `digest.py`:

```python
SECTIONS = ["Top stories", "AI models & labs", "Industry & funding", "Policy & society", "Research & tools"]
```

Edit the list. The prompt passes it to the model in order and tells it to omit empty sections. The rule that "Top stories" holds the 3–4 biggest stories is in `PROMPT` just below; update it if you rename or remove that section.

### Change the subject prefix, From name or To name

```yaml
email:
  subject_prefix: "Morning Tech Brief"
  from_name: "Tech Brief"
  to_name: "Noah"
```

### Switch the LLM model or provider

The script uses the `openai` Python package against any **OpenAI-compatible** chat-completions endpoint, with JSON mode (`response_format={"type": "json_object"}`).

**Models:** the primary model comes from the `LLM_MODEL` env var, falling back to `DEFAULT_LLM_MODEL` in `digest.py` (currently `gemini-3.5-flash`). The lighter fallback model comes from `LLM_LITE_MODEL`, falling back to `DEFAULT_LLM_LITE_MODEL` (currently `gemini-3.5-flash-lite`). `gemini-3.8-flash` was the default until October 2026, but it frequently returned 503/429 or hung, which caused the fallback emails and a cancelled run.

- Locally: add `LLM_MODEL=…` / `LLM_LITE_MODEL=…` to `.env`.
- On GitHub: the workflow does **not** pass these today, so the defaults are always used. Either change `DEFAULT_LLM_MODEL` in `digest.py`, or add a repository *variable* (Settings → Secrets and variables → Actions → Variables) and pass it in the workflow's `env:` block:
  ```yaml
            LLM_MODEL: ${{ vars.LLM_MODEL }}
  ```

To see which model names your key can use:

```bash
.venv/bin/python -c "
import os; from dotenv import load_dotenv; from openai import OpenAI
load_dotenv()
c = OpenAI(api_key=os.environ['LLM_API_KEY'], base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
print('\n'.join(sorted(m.id for m in c.models.list())))
"
```

A name in this list isn't a guarantee: `gemini-2.5-flash` is listed but returns 404 for chat. Test a model with a real dry run before switching.

**Provider:** the base URL is a constant in `digest.py`, **not** an env var:

```python
LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
```

To switch providers (OpenAI, OpenRouter, a local server, …), change `LLM_BASE_URL` and `DEFAULT_LLM_MODEL`, and put that provider's key in the `LLM_API_KEY` secret. The provider must support JSON mode. If you want it configurable without code edits, change the line to `LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai/"` and pass `LLM_BASE_URL` in the workflow.

---

## Secrets

The workflow reads seven repository secrets and exposes them to the script as environment variables of the same name.

| Secret | What it is | Where it comes from | Example (placeholder) |
| --- | --- | --- | --- |
| `LLM_API_KEY` | Gemini API key | [Google AI Studio](https://aistudio.google.com/) → Get API key | `<your-gemini-api-key>` |
| `SMTP_HOST` | iCloud SMTP server | Apple's iCloud Mail settings | `smtp.mail.me.com` |
| `SMTP_PORT` | SMTP port (STARTTLS) | Apple's iCloud Mail settings. Defaults to 587 if empty. | `587` |
| `SMTP_USER` | Login for SMTP: your primary iCloud Mail address | Your Apple account | `<you>@icloud.com` |
| `SMTP_PASSWORD` | An **app-specific password**, not your Apple account password | [account.apple.com](https://account.apple.com) → Sign-In and Security → App-Specific Passwords | `<app-specific-password>` |
| `EMAIL_TO` | Where the digest is delivered | You choose | `<you>@icloud.com` |
| `EMAIL_FROM` | The iCloud alias the digest is sent from. If empty or missing, the script sends from `SMTP_USER`. | iCloud Mail → Settings → Accounts → add an alias | `<your-alias>@icloud.com` |

If `EMAIL_FROM` is missing the run still works. If any of the others is missing the run fails (a `KeyError` in the logs), except `SMTP_PORT`, which falls back to 587.

**Update a secret:** GitHub repo → **Settings** → **Secrets and variables** → **Actions** → click the secret → **Update secret** → paste the new value → save. The next run uses it; no code change or commit needed.

> GitHub Secrets **can't be viewed after saving**, only replaced. Keep a copy of each value in a password manager.

---

## Running locally (optional)

Requires Python 3.13.

```bash
git clone https://github.com/Nsher02/ai-daily-news-digest.git
cd ai-daily-news-digest
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create `.env` in the project root. `digest.py` loads it with `python-dotenv`; real environment variables take precedence.

```dotenv
LLM_API_KEY=<your-gemini-api-key>
SMTP_HOST=smtp.mail.me.com
SMTP_PORT=587
SMTP_USER=<you>@icloud.com
SMTP_PASSWORD=<app-specific-password>
EMAIL_TO=<you>@icloud.com
EMAIL_FROM=<your-alias>@icloud.com
# optional:
# LLM_MODEL=gemini-3.5-flash
# LLM_LITE_MODEL=gemini-3.5-flash-lite
```

**Dry run** (fetches and summarizes for real, but saves `digest.html` and prints the plain-text version instead of emailing):

```bash
.venv/bin/python digest.py --dry-run
open digest.html
```

**Real send:**

```bash
.venv/bin/python digest.py
```

> **Never commit `.env`.** It's in `.gitignore`; keep it that way. Check `git status` before every commit.

Logs go to stderr as `LEVEL message`. The `openai` package logs one `INFO HTTP Request: POST …` line per call; it shows the URL and status, never the key.

---

## Maintenance and troubleshooting

### A red Actions run

Open **Actions** → the failed run → the **digest** job → expand **Build and send digest** (or **Install dependencies** if it failed earlier). Errors are lines starting with `ERROR`, or a Python traceback at the end. The workflow also emails you "AI Daily News Digest failed – check GitHub Actions" when any step fails.

| Symptom in the log | Likely cause | Fix |
| --- | --- | --- |
| `KeyError: 'SMTP_USER'` (or another name) | A secret is missing or misnamed. Names are case-sensitive and must match the table above exactly. | Add or rename the secret. |
| `sending email failed: (535, …)` or another auth error | App-specific password revoked or wrong; `SMTP_USER` wrong. | Generate a new app-specific password and update `SMTP_PASSWORD`. |
| `sending email failed` mentioning the sender address | `EMAIL_FROM` isn't an active alias on the `SMTP_USER` account. | Fix the alias, or delete the `EMAIL_FROM` secret to send from `SMTP_USER`. |
| `LLM pass N attempt N (…) failed …: HTTP 503` or `HTTP 429` | Gemini overloaded or rate-limited. A later attempt usually succeeds. If all fail, the email goes out as raw headlines and the run stays **green**. | Usually transient. If it happens daily, check your quota in AI Studio or switch `DEFAULT_LLM_MODEL`. |
| `LLM pass N attempt N (…) failed …: APITimeoutError` | A request hung past the 60s timeout. | Transient; the chain moves on. |
| `LLM pass N attempt N (…) failed …: HTTP 400`/`401`/`403`/`404` | Bad or revoked `LLM_API_KEY`, or the model name no longer exists. | Rotate the key, or update `DEFAULT_LLM_MODEL` / `DEFAULT_LLM_LITE_MODEL`. |
| `LLM summary failed … LLM step hit the 600s hard cap` | Every attempt hung; the watchdog stopped the step and sent raw headlines. | Transient Gemini outage; no action unless it repeats. |
| `429 … Generate content requests per day limit exceeded` | The free tier's 20 requests/day for that model is used up (usually from many manual test runs). The chain skips straight to Flash-Lite. | Wait for the daily reset; avoid many test runs in one day. |
| `paragraph summaries failed, using short summaries` | Pass 2 failed on every attempt. The email still has the pass-1 short summaries. | Transient; no action unless it repeats. |
| `article fetch failed for <url>` / `could not resolve Google News link` | A paywall, block or timeout on one article. That story gets a shorter snippet-based summary. | None; normal for a few stories a day. |
| `Skipping: today's digest was already sent by run …` | Normal for the later morning firings after the first one sent. | None. |
| `Skipping: … outside the 07:45-10:00 Chicago send window` | Normal for the firings that land before 7:45 AM (and after 10:00 AM). | None. |
| `ERROR <feed>: failed, skipping (…)` | One feed is down, moved, or blocking the request. The run continues and stays green. | If it repeats for days, fix or remove the URL in `config.yaml`. |
| `Error: The operation was canceled` after 20 minutes | Hit `timeout-minutes: 20`. Shouldn't happen, since the LLM step is capped at 10 minutes. | Rerun, and check which step was slow. |

### Changing your Apple account password

Changing your Apple account password **revokes all app-specific passwords**. The next run will fail at login. Generate a new app-specific password at account.apple.com → Sign-In and Security → App-Specific Passwords, then update the `SMTP_PASSWORD` secret (and your local `.env`).

### Rotating the Gemini key

1. In Google AI Studio, create a new API key.
2. Update the `LLM_API_KEY` secret on GitHub (and in `.env`).
3. Trigger a manual run and confirm the email has AI summaries, not the raw-headlines fallback.
4. Delete the old key in AI Studio.

### The iCloud alias (`EMAIL_FROM`)

- The script **logs in** as `SMTP_USER` but puts `EMAIL_FROM` on the From line. iCloud only accepts From addresses that belong to the logged-in account, so the alias must exist and be enabled on that same account.
- The **display name** ("AI News") comes from `email.from_name` in `config.yaml`, not from the alias's own name setting in iCloud.
- iCloud Mail's own "send from" default (in iCloud Mail settings) only affects mail you write in the Mail apps. The script sets the From header explicitly, so it doesn't depend on that setting.
- To stop using the alias, delete the `EMAIL_FROM` secret (or leave it empty); the script falls back to `SMTP_USER`.

### If the repo is ever made public

The repo is currently private. In a **public** repository, GitHub automatically disables scheduled workflows after **60 days with no repository activity**. If that happens, re-enable the workflow from the Actions tab or push any commit. Also review what's committed (`prompts/`, `digest.html`) before making it public.

### Cost

- **Gemini:** 2 requests per day on a normal run (pass 1 + pass 2; at most 11 on a very bad day). The free tier allows **20 requests per day per model**, so a manual test run or two is fine, but many test runs in one day will hit `429 … PerDay` and fall back to Flash-Lite until the quota resets. Free-tier limits and model availability change over time; check AI Studio if you start seeing 429s.
- **GitHub Actions:** a normal run takes a minute or two, and the skipped GitHub cron firings each take a few seconds. cron-job.org is free. A run where Gemini is down can take about 12 minutes because of the 10-minute LLM cap. Public repos get free minutes on standard runners; private repos draw from the account's monthly included minutes (2,000 on the Free plan), so a daily run uses only a small fraction.
- **iCloud Mail:** included with your Apple account.


## Offline regression checks

Run `.venv/bin/python -m unittest discover -s tests -v`. Tests cover delivery outcomes, the send window (CST, CDT, DST switch days, receipts, early manual runs, external trigger vs GitHub cron, manual always sends), duplicate evidence preservation, TLDR parsing and fallback, editorial validation, and short-selection retry behavior. SMTP and Gemini are mocked; tests do not send email or consume API quota. The TLDR parser was also checked against the public October 30, 2026 issue.

Implementation prompts are in `prompts/prompt_12_track_email_delivery.md` through `prompts/prompt_15_validate_editorial_output.md`, executed sequentially with checks after each stage.


## Run summaries and offline replay

Each executed digest writes a GitHub Actions step summary with successful/configured feeds, grouped candidates, selected stories, retrieved articles, LLM attempts, summary quality (`full`, `partial_pass_2`, `pass_1`, `raw_headlines`, or `none`), deadline status, and send outcome. A feed returning zero recent items still counts as a successful fetch. Attempt counts are saved before each model call, so a killed worker's in-flight attempt is included. Article counts include completed fetch results even if another worker hangs. Skipped backup runs report the existing receipt. A runner killed outside the supervised LLM stage may prevent the final summary from being written.

To save a snapshot during a live dry run (fetches feeds and calls Gemini, but does not send email):

```sh
.venv/bin/python digest.py --dry-run --save-replay /private/tmp/digest-replay.json --output /private/tmp/digest-preview.html
```

To reparse successful saved model replies and render fully offline:

```sh
.venv/bin/python digest.py --replay /private/tmp/digest-replay.json --output /private/tmp/digest-replayed.html
```

Replay returns before loading `.env`, fetching feeds, constructing the API client, or sending email. It never writes a sent receipt. It preserves the original digest date. Raw-headline snapshots render without model replies. If parser changes reorder or remove selected stories, replay rejects saved pass-2 numbering rather than attaching a summary to the wrong story.

Snapshots contain source text, article excerpts, selected stories and successful model replies; they explicitly omit credentials and environment variables. Save personal snapshots outside the repository. For an immediate synthetic offline example, use `tests/fixtures/replay.json` as the replay input. These snapshots support parser/rendering development; they do not measure how a live model responds to edited prompts.

Prompts 16–18 implement grounding, subprocess deadlines, and summaries/replay sequentially. Regression tests include malformed JSON, partial rewrites, article failures, deadline exhaustion, real sleeping subprocess termination, saved checkpoints, replay isolation, and delivery outcomes. No additional runtime dependencies were introduced.
