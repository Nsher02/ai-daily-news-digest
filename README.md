# ai-daily-news-digest

A personal daily email digest of AI news, delivered to an iCloud inbox every morning. A single Python script pulls 13 RSS feeds, asks Google Gemini to pick and summarize the most important stories, and sends a mobile-friendly HTML email through iCloud SMTP. GitHub Actions runs it on a schedule, so nothing needs to stay running on your machine.

---

## How it works

Everything lives in `digest.py`; `main()` runs these steps in order.

| # | Step | Function | What happens |
| --- | --- | --- | --- |
| 1 | Fetch | `fetch_all` / `fetch_feed` | Downloads each feed in `config.yaml` with `requests` (timeout `request_timeout`, browser-like `user_agent`) and parses it with `feedparser`. Google News titles lose their ` - Publisher` suffix and the publisher becomes the source; TLDR AI's empty issue items are filled in from the issue page (`fetch_issue_stories`). |
| 2 | Filter | `fetch_feed` | Keeps items published in the last `lookback_hours`. Items with no date are dropped (logged as a warning). Each feed is sorted newest first and capped at its `max_items`. |
| 3 | Dedupe | `dedupe` | Drops an item if its **normalized URL** or **normalized title** was already seen. The first occurrence wins, in feed order. |
| 4 | Summarize | `summarize` / `run_llm_chain` | Sends all items to Gemini in one request. The model picks `min_stories`–`max_stories` stories (10–15), merges duplicates, ranks multi-source stories higher, sorts them into sections, and returns JSON. Wrapped in a retry/fallback chain with a hard time cap (see [Failure behavior](#failure-behavior)). |
| 5 | Render | `render_html` / `render_text` | Builds an inline-CSS HTML email (600px card, table layout) plus a plain-text alternative. |
| 6 | Send | `send_email` | Connects to `SMTP_HOST:SMTP_PORT`, upgrades with STARTTLS, logs in as `SMTP_USER`, sends from `EMAIL_FROM`. |

**Normalization used by dedupe:**
- URL: lowercase scheme and host, strip `www.`, drop `utm_*` query params, the `#fragment` and a trailing `/`. Other query params are kept (so `?id=1` and `?id=2` stay distinct).
- Title: lowercase, curly quotes → straight, punctuation removed, whitespace collapsed.

This only catches *exact* duplicates. The same story covered by two outlets with different headlines gets through dedupe, and the LLM merges it in step 4. The prompt treats a story covered by several sources as a strong signal of importance: it ranks higher and lists every source. It also prioritizes major model releases, big company and lab news, funding and policy over minor product updates.

### The ID-mapping design (why links can't be invented)

Each item goes into the prompt as `[id] (source) title` plus a snippet. The model is told to return only item **IDs**, never URLs:

```json
{"tldr": "...", "sections": [{"name": "...", "stories": [{"ids": [3, 17], "headline": "...", "summary": "..."}]}]}
```

The code then maps each ID back to the real feed item and attaches *that item's* link and source name. Any ID that isn't an integer in range is logged and ignored; a story left with no valid IDs is dropped. A merged story gets one link per source (for example "Hacker News · Ars Technica"), and its headline links to the first one.

### The "(title only)" anti-hallucination rule

Some feeds carry no real description. Hacker News (hnrss) fills the summary with boilerplate like `Article URL: … Comments URL: … Points: 132 # Comments: 72`. `clean_text` strips HTML tags and that boilerplate (`FEED_BOILERPLATE`) and truncates to 300 characters (or the feed's `snippet_chars`; TLDR AI uses 1500 because one item holds a whole newsletter issue). Google News summaries only repeat the title, so they're dropped. If nothing is left, the item is sent to the model marked **`(title only)`**.

The prompt tells the model to summarize those items using only what the headline says ("HN discussion of …"), and never to add details, causes, numbers or quotes that aren't in the title or snippet. Temperature is `0.2` to keep output conservative.

### Failure behavior

| Situation | What happens | Exit code |
| --- | --- | --- |
| One feed fails (timeout, HTTP error, unparseable) | Logged as `ERROR <feed>: failed, skipping`; the run continues with the other feeds. **No retry.** | 0 |
| No items at all after fetch + dedupe | Logs `no items at all; nothing to send` and **sends nothing**. | 0 |
| Gemini error (503, 429, timeout, bad JSON, zero usable stories) | Runs the LLM fallback chain below. If every step fails, the email is sent anyway as a **raw-headlines fallback**: every item grouped by source, under a yellow note saying "The AI summary failed today…". | 0 |
| Sending the email fails (bad login, SMTP down) | Logs `sending email failed: …` and exits non-zero so the GitHub run shows **red**. The SMTP connection has a 30s timeout. | 1 |

**LLM fallback chain** (`run_llm_chain`, all values in `config.yaml`):

1. Primary model (`gemini-3.5-flash`), **60s timeout per request** (`llm_timeout`).
2. Up to **3 retries** of the primary with exponential backoff of 2s, 4s, 8s (`llm_retries`, `llm_backoff`). Errors 400/401/403/404 skip the remaining retries, since retrying the same model won't help.
3. The lighter model (`gemini-3.5-flash-lite`) **once**.
4. Wait **5 minutes** (`llm_final_wait`), then the primary one last time.
5. Only then: the raw-headlines fallback email.

If the model returns fewer than `min_stories` stories, that counts as a failed attempt, but the short digest is kept and used if nothing better comes back. Every failed attempt logs the exact cause, for example `ERROR LLM attempt 1 (gemini-3.5-flash) failed after 4s: HTTP 503 InternalServerError: [{"error": {"code": 503, "message": "This model is currently experiencing high demand. …"}}]`.

**Hard cap:** the whole LLM step finishes within **10 minutes** (`llm_step_cap: 600`) no matter what. The chain shortens the 5-minute wait if needed so the last attempt fits, and a watchdog thread gives up on the step at the cap even if a request hangs and ignores its timeout. Worst case: about 4.5 min of primary attempts, 1 min of Flash-Lite, a wait shortened to about 3.5 min, then 1 min for the final try.

---

## Project files

| Path | Purpose |
| --- | --- |
| `digest.py` | The whole pipeline: fetch, filter, dedupe, LLM summary, render, send. Also holds the LLM prompt, the section list, the model default and the API base URL. |
| `config.yaml` | Feeds and settings you'll edit most often (see [Configuration](#configuration-how-to-edit)). |
| `requirements.txt` | Pinned dependencies: `feedparser`, `openai`, `python-dotenv`, `PyYAML`, `requests`. |
| `.github/workflows/daily-digest.yml` | The GitHub Actions workflow: primary + backup schedule, skip-if-already-sent guard, Python setup, secrets → env vars, runs `python digest.py`. |
| `prompts/` | The step-by-step build prompts used to create this project with Claude Code (`prompt_0_brief.md` … `prompt_10_fix_all.md`). History only; nothing reads them at runtime. |
| `.claude/` | Claude Code project settings (`settings.json` holds tool-permission rules). Not used by the digest. |
| `.gitignore` | Standard Python template plus `.env` and `.venv`. Keeps secrets and the virtualenv out of git; `__pycache__/` is ignored too. |
| `digest.html` | Output of the last `--dry-run`. It's committed, so a dry run will show it as modified in `git status`. |
| `README.md` | This file. |

---

## Schedule

The workflow has a **primary** and a **backup** scheduled run, both in America/Chicago time:

```yaml
on:
  schedule:
    - cron: "53 7 * * *" # primary: 7:53 AM Central
      timezone: "America/Chicago"
    - cron: "23 8 * * *" # backup: 8:23 AM Central
      timezone: "America/Chicago"
  workflow_dispatch:
```

Both times are deliberately **off the top of the hour**. GitHub is busiest at :00 and drops or delays scheduled runs then (the old `0 8 * * *` schedule once never fired at all).

**Skip guard:** the first step of a *scheduled* run uses the preinstalled `gh` CLI (`GH_TOKEN: ${{ github.token }}`, with `permissions: actions: read` and `contents: read`) to check whether a successful run of this workflow already finished **today**, by America/Chicago date. If one did, every later step is skipped, so the backup only sends when the primary failed or never fired. Manual `workflow_dispatch` runs never run the guard and always send. A `concurrency` group makes a backup that starts while a delayed primary is still running wait for it, then skip.

The `timezone` field takes an IANA name and GitHub handles daylight saving, so the times stay local all year. Without `timezone`, cron times are UTC.

**To change the time or time zone**, edit both places so the email date matches the send time:

1. `.github/workflows/daily-digest.yml`: both `cron` entries (minute hour), their `timezone`, and the `TZ=America/Chicago` used by the skip guard. Example for 6:37 AM Pacific with a 7:07 backup:
   ```yaml
       - cron: "37 6 * * *"
         timezone: "America/Los_Angeles"
       - cron: "7 7 * * *"
         timezone: "America/Los_Angeles"
   ```
2. `config.yaml`: `settings.timezone` (used for the date in the subject and heading):
   ```yaml
     timezone: America/Los_Angeles
   ```

**Runs can start late.** GitHub queues scheduled runs and they often start several minutes (sometimes much more) after the cron time; under heavy load a run can be skipped entirely, which is what the backup run is for. Keep both times off the top of the hour. Scheduled runs only fire from the default branch (`main`).

**Manual run:** GitHub → **Actions** → **AI Daily News Digest** → **Run workflow** → branch `main` → **Run workflow**. This sends a real email.

The job runs on `ubuntu-latest` with Python 3.13, caches pip, and has a **20-minute** timeout (`timeout-minutes: 20`), comfortably above the 10-minute LLM cap.

---

## Configuration (how to edit)

### `config.yaml` reference

| Key | Current value | Controls |
| --- | --- | --- |
| `settings.lookback_hours` | `26` | How far back to keep items. 26 rather than 24 gives slack for late runs and odd feed timestamps. |
| `settings.timezone` | `America/Chicago` | Time zone for the date in the subject and email heading. Does **not** control when the workflow runs. |
| `settings.request_timeout` | `20` | Seconds per feed request. |
| `settings.min_stories` | `10` | Minimum stories in the email whenever enough items exist. |
| `settings.max_stories` | `15` | Max stories the LLM is asked to pick. |
| `settings.llm_timeout` | `60` | Seconds per Gemini request (per attempt). |
| `settings.llm_retries` | `3` | Retries of the primary model. |
| `settings.llm_backoff` | `2` | Seconds before the first retry; doubles each time (2, 4, 8). |
| `settings.llm_final_wait` | `300` | Seconds to wait before the last try of the primary model (shortened if needed to fit the cap). |
| `settings.llm_step_cap` | `600` | Hard cap on the whole LLM step, in seconds. |
| `settings.user_agent` | browser UA string | Sent with feed requests; some sites block default Python agents. |
| `email.subject_prefix` | `AI Daily News Digest` | Subject is `<prefix> — <Weekday, Month Day>`. Also the big heading at the top of the email. |
| `email.from_name` | `AI News` | Display name on the From line. |
| `email.to_name` | `Noah Sher` | Display name on the To line. |
| `feeds[]` | 13 feeds | Each has `name` (shown in the email), `url` and `max_items` (cap per run). Optional: `snippet_chars` (snippet length sent to the LLM, default 300), `strip_publisher: true` (Google News: strip ` - Publisher` from titles and show the publisher as the source), `expand_issue: true` (TLDR: read the issue's stories from its web page). |

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
| TLDR AI | 5 | One empty item per newsletter issue (weekdays only); stories are pulled from the issue page and sent with a 1500-char snippet. |
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

To remove one, delete its three lines. Feed order matters slightly: when dedupe finds duplicates, the feed listed first keeps its copy. Test a new feed with a dry run (see [Running locally](#running-locally-optional)); a bad URL shows up as `ERROR <name>: failed, skipping`.

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

Open **Actions** → the failed run → the **digest** job → expand **Build and send digest** (or **Install dependencies** if it failed earlier). Errors are lines starting with `ERROR`, or a Python traceback at the end. GitHub also emails you about failed scheduled runs by default.

| Symptom in the log | Likely cause | Fix |
| --- | --- | --- |
| `KeyError: 'SMTP_USER'` (or another name) | A secret is missing or misnamed. Names are case-sensitive and must match the table above exactly. | Add or rename the secret. |
| `sending email failed: (535, …)` or another auth error | App-specific password revoked or wrong; `SMTP_USER` wrong. | Generate a new app-specific password and update `SMTP_PASSWORD`. |
| `sending email failed` mentioning the sender address | `EMAIL_FROM` isn't an active alias on the `SMTP_USER` account. | Fix the alias, or delete the `EMAIL_FROM` secret to send from `SMTP_USER`. |
| `LLM attempt N (…) failed …: HTTP 503` or `HTTP 429` | Gemini overloaded or rate-limited. A later attempt usually succeeds. If all fail, the email goes out as raw headlines and the run stays **green**. | Usually transient. If it happens daily, check your quota in AI Studio or switch `DEFAULT_LLM_MODEL`. |
| `LLM attempt N (…) failed …: APITimeoutError` | A request hung past the 60s timeout. | Transient; the chain moves on. |
| `LLM attempt N (…) failed …: HTTP 400`/`401`/`403`/`404` | Bad or revoked `LLM_API_KEY`, or the model name no longer exists. | Rotate the key, or update `DEFAULT_LLM_MODEL` / `DEFAULT_LLM_LITE_MODEL`. |
| `LLM summary failed … LLM step hit the 600s hard cap` | Every attempt hung; the watchdog stopped the step and sent raw headlines. | Transient Gemini outage; no action unless it repeats. |
| `A successful run already finished today …; skipping.` | Normal for the backup run when the primary already sent. | None. |
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

The repo is currently private. In a **public** repository, GitHub automatically disables scheduled workflows after **60 days with no repository activity**. If that happens, re-enable the workflow from the Actions tab or push any commit. Also review what's committed (`prompts/`, `.claude/`, `digest.html`) before making it public.

### Cost

- **Gemini:** usually one or two requests per day (more on bad days, at most six), well within the Gemini API free tier. Free-tier limits and model availability change over time; check AI Studio if you start seeing 429s.
- **GitHub Actions:** each run takes a minute or two. Public repos get free minutes on standard runners; private repos draw from the account's monthly included minutes (2,000 on the Free plan), so a daily run uses only a small fraction.
- **iCloud Mail:** included with your Apple account.
