"""Daily AI news digest."""

import argparse
import calendar
import copy
import html
import json
import logging
import os
import re
import smtplib
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
import trafilatura
import yaml
from dotenv import load_dotenv
import openai
from openai import OpenAI

CONFIG_PATH = Path(__file__).parent / "config.yaml"
LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_LLM_MODEL = "gemini-3.5-flash"
DEFAULT_LLM_LITE_MODEL = "gemini-3.5-flash-lite"
NO_RETRY_STATUSES = {400, 401, 403, 404}  # retrying the same model won't help
SECTIONS = ["Top stories", "AI models & labs", "Industry & funding", "Policy & society", "Research & tools"]

PROMPT = """You are editing a daily AI news digest for a CS grad student / software engineer.

Below are today's items, each with a numeric ID and its source. Pick the {min_stories}-{max_stories} most important stories.
- Always return at least {min_stories} stories when the list has that many distinct stories.
- Merge items that cover the same story into one story listing all their IDs.
- A story covered by several sources is a strong signal of importance: rank it higher and list every one of its IDs.
- Prioritize major model releases, big company and lab news, funding and acquisitions, and policy/regulation over minor product updates, tutorials and opinion pieces.
- Skip promos, event ads, sponsored posts, listicles and fluff.
- Group stories into these sections, in this order (omit empty ones): {sections}.
- "Top stories" holds the 3-4 biggest stories of the day; don't repeat them in other sections.
- Within each section, order stories from most to least important.
- Write an original headline and a 1-2 sentence factual summary for each story.
- Some items are marked "(title only)". For those, summarize ONLY what the headline itself says (e.g. "HN discussion of …" / "Post about …").
- Never add details, causes, numbers or quotes that aren't in the item's title or snippet. If unsure, keep it short and say less.
- Write a 2-3 sentence "tldr" of the day.
- Use only IDs from the list. Do not include URLs.

Return ONLY JSON in this exact shape:
{{"tldr": "...", "sections": [{{"name": "...", "stories": [{{"ids": [1, 2], "headline": "...", "summary": "..."}}]}}]}}

Items:
{items}"""

SUMMARY_PROMPT = """You are writing the story summaries for a daily AI news digest read by a CS grad student / software engineer.

For each numbered story below, write ONE paragraph:
- If ARTICLE TEXT is given: 4-6 sentences covering what happened, the key details and numbers, and why it matters.
- If the article text is unavailable: 1-3 sentences using only the headline and feed items. Do not pad it.
- Use ONLY facts stated in that story's article text, feed items and headline. Never add names, numbers, dates, quotes, causes or background from your own knowledge.
- "Why it matters" must follow from what the text says; if the text gives no reason, leave it out rather than guess.
- Plain, neutral, factual prose. No bullet points, no hype, no "the article says".

Return ONLY JSON in this exact shape, one entry per story:
{{"stories": [{{"n": 1, "summary": "..."}}]}}

{stories}"""

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("digest")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def entry_time(entry):
    """Return the entry's publish/update time as an aware UTC datetime, or None."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return None


def fetch_issue_stories(url, settings):
    """TLDR's feed has one empty item per newsletter issue; pull the issue's stories from its page."""
    resp = requests.get(url, timeout=settings["request_timeout"], headers={"User-Agent": settings["user_agent"]})
    resp.raise_for_status()
    stories = []
    for chunk in resp.text.split("<h3")[1:]:
        heading, _, rest = chunk.partition("</h3>")
        title = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", "<h3" + heading)).split())
        if not title.endswith(")") or "(Sponsor)" in title:
            continue  # section headers and ads
        blurb = clean_text(rest.split("<h", 1)[0], 160)
        stories.append(f"{title}: {blurb}")
    return " | ".join(stories)


IMG_TAG = re.compile(r'<img[^>]+src="([^"]+)"', re.I)


def feed_image(entry):
    """The entry's image from media:content, media:thumbnail, an enclosure or an <img> in its HTML."""
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        if media.get("url") and media.get("medium", "image") == "image":
            return media["url"]
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image/"):
            return link["href"]
    body = entry.get("summary", "") + "".join(c.get("value", "") for c in entry.get("content", []))
    match = IMG_TAG.search(body)
    return html.unescape(match.group(1)) if match else ""


def fetch_feed(feed, settings, cutoff):
    """Fetch one feed and return its recent items, newest first, capped at max_items."""
    resp = requests.get(
        feed["url"],
        timeout=settings["request_timeout"],
        headers={"User-Agent": settings["user_agent"]},
    )
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"could not parse feed: {parsed.bozo_exception}")

    items = []
    undated = 0
    for entry in parsed.entries:
        published = entry_time(entry)
        if published is None:
            undated += 1
            continue
        if published < cutoff:
            continue
        title = html.unescape(entry.get("title", "")).strip()
        source = feed["name"]
        summary = entry.get("summary", "")
        if feed.get("strip_publisher"):
            # Google News titles end with " - Publisher"; its summary just repeats the title.
            headline, sep, publisher = title.rpartition(" - ")
            if sep and headline:
                title, source = headline.strip(), publisher.strip()
            source = entry.get("source", {}).get("title") or source
            if source.startswith("http"):
                source = urlsplit(source).netloc.removeprefix("www.") or source
            summary = ""
        if feed.get("expand_issue") and not summary:
            try:
                summary = fetch_issue_stories(entry.get("link", ""), settings)
            except Exception as e:
                log.warning("%s: could not fetch issue page (%s)", feed["name"], e)
        items.append({
            "source": source,
            "title": title,
            "link": entry.get("link", ""),
            "summary": summary,
            "snippet_chars": feed.get("snippet_chars", 300),
            "image": feed_image(entry),
            "published": published,
        })
    if undated:
        log.warning("%s: skipped %d undated entries", feed["name"], undated)

    items.sort(key=lambda i: i["published"], reverse=True)
    return items[: feed["max_items"]]


def fetch_all(config):
    settings = config["settings"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings["lookback_hours"])
    results = {}
    for feed in config["feeds"]:
        try:
            results[feed["name"]] = fetch_feed(feed, settings, cutoff)
        except Exception as e:
            log.error("%s: failed, skipping (%s)", feed["name"], e)
    return results


def normalize_url(url):
    """Lowercase host, drop www., utm_* params, fragment and trailing slash."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ])
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def normalize_title(title):
    """Lowercase, unify curly quotes, strip punctuation and collapse whitespace."""
    title = title.lower().replace("’", "'").replace("‘", "'")
    title = re.sub(r"[^\w\s]", "", title)
    return " ".join(title.split())


def dedupe(items):
    """Keep the first item for each normalized URL or title; return (kept, dropped)."""
    seen_urls, seen_titles = set(), set()
    kept, dropped = [], []
    for item in items:
        url_key = normalize_url(item["link"]) if item["link"] else None
        title_key = normalize_title(item["title"]) or None
        if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
            dropped.append(item)
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        kept.append(item)
    return kept, dropped


FEED_BOILERPLATE = re.compile(r"(Article URL|Comments URL):\s*\S+|Points:\s*\d+|# Comments:\s*\d+")


def clean_text(text, limit):
    """Strip HTML tags, feed boilerplate (hnrss link/points lines) and whitespace runs, then truncate."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = " ".join(FEED_BOILERPLATE.sub(" ", text).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def build_prompt(items, settings):
    lines = []
    for i, item in enumerate(items):
        snippet = clean_text(item["summary"], item["snippet_chars"])
        lines.append(f"[{i}] ({item['source']}) {item['title']}\n    {snippet or '(title only)'}")
    return PROMPT.format(
        min_stories=settings["min_stories"],
        max_stories=settings["max_stories"],
        sections=", ".join(SECTIONS),
        items="\n".join(lines),
    )


def parse_digest(content, items):
    """Pass-1 JSON -> digest; real links and items are attached by ID."""
    data = json.loads(content)
    sections = []
    for section in data.get("sections", []):
        stories = []
        for story in section.get("stories", []):
            ids = [i for i in story.get("ids", []) if isinstance(i, int) and 0 <= i < len(items)]
            invalid = [i for i in story.get("ids", []) if i not in ids]
            if invalid:
                log.warning("ignoring invalid IDs %s for %r", invalid, story.get("headline"))
            if not ids:
                continue
            links = [{"source": items[i]["source"], "url": items[i]["link"]} for i in ids]
            stories.append({
                "headline": story.get("headline", "").strip(),
                "summary": story.get("summary", "").strip(),
                "url": links[0]["url"],
                "links": links,
                "ids": ids,
                "image": "",
            })
        if stories:
            sections.append({"name": section.get("name", ""), "stories": stories})
    if not sections:
        raise ValueError("model returned no usable stories")
    return {"tldr": data.get("tldr", "").strip(), "note": "", "sections": sections}


def describe_error(e):
    """Status code and message of an LLM failure, for the Actions log."""
    if isinstance(e, openai.APIStatusError):
        detail = json.dumps(e.body)[:500] if e.body else e.message
        return f"HTTP {e.status_code} {type(e).__name__}: {detail}"
    return f"{type(e).__name__}: {e}"


def run_llm_chain(prompt, parse, settings, deadline, label, final_try=True, count=None, want=0):
    """Primary model with retries, then the lite model once, then (optionally) the primary after a long wait.

    parse(content) turns the model's reply into a result or raises. If count(result) < want, the result
    is kept as a fallback and the chain keeps trying for a better one.
    """
    timeout = settings["llm_timeout"]
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=LLM_BASE_URL, max_retries=0, timeout=timeout)
    primary = os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL
    lite = os.environ.get("LLM_LITE_MODEL") or DEFAULT_LLM_LITE_MODEL

    attempts = [(primary, 0)]
    attempts += [(primary, settings["llm_backoff"] * 2**i) for i in range(settings["llm_retries"])]
    attempts += [(lite, 0)]
    if final_try:
        attempts += [(primary, settings["llm_final_wait"])]
    dead_models, short, last_error = set(), None, None

    for n, (model, wait) in enumerate(attempts, 1):
        final = final_try and n == len(attempts)
        if model in dead_models or (final and short):
            continue
        if final:
            # Shorten the long wait so the last attempt still gets a full timeout before the cap.
            wait = min(wait, deadline - time.monotonic() - timeout)
        if wait > 0:
            log.info("LLM %s: waiting %ds before attempt %d", label, wait, n)
            time.sleep(wait)
        remaining = deadline - time.monotonic()
        if remaining < 1:
            break
        started = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=min(timeout, remaining),
            )
            result = parse(resp.choices[0].message.content)
        except Exception as e:
            last_error = e
            log.error("LLM %s attempt %d (%s) failed after %.0fs: %s",
                      label, n, model, time.monotonic() - started, describe_error(e))
            if isinstance(e, openai.APIStatusError) and (
                    e.status_code in NO_RETRY_STATUSES
                    or (e.status_code == 429 and "PerDay" in json.dumps(e.body))):  # daily quota: retrying won't help
                dead_models.add(model)
            continue
        got = count(result) if count else want
        log.info("LLM %s attempt %d (%s) succeeded in %.0fs (%d)", label, n, model, time.monotonic() - started, got)
        if got >= want:
            return result
        log.warning("LLM %s returned only %d (want %d); trying again", label, got, want)
        short = result
    if short:
        return short
    raise last_error or TimeoutError(f"LLM {label} ran out of time")


def story_count(digest):
    return sum(len(s["stories"]) for s in digest["sections"])


def decode_google_news(url, settings):
    """Resolve a news.google.com/rss/articles/… redirect to the publisher's URL, or return None."""
    headers = {"User-Agent": settings["user_agent"]}
    try:
        article_id = urlsplit(url).path.rstrip("/").split("/")[-1]
        page = requests.get(f"https://news.google.com/rss/articles/{article_id}", headers=headers,
                            timeout=settings["article_timeout"]).text
        sig = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sig and ts):
            return None
        payload = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None,
                                   None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                   article_id, int(ts.group(1)), sig.group(1)]
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data={"f.req": json.dumps([[["Fbv4je", json.dumps(payload), None, "generic"]]])},
            timeout=settings["article_timeout"],
        )
        decoded = json.loads(json.loads(resp.text.split("\n\n")[1])[0][2])[1]
        return decoded if decoded.startswith("http") else None
    except Exception as e:
        log.warning("could not resolve Google News link (%s)", type(e).__name__)
        return None


def fetch_article(url, settings):
    """Main text (trimmed) and og:image of an article page."""
    resp = requests.get(url, timeout=settings["article_timeout"], headers={"User-Agent": settings["user_agent"]})
    resp.raise_for_status()
    text = trafilatura.extract(resp.text, url=url, include_comments=False, include_tables=False) or ""
    meta = trafilatura.extract_metadata(resp.text)
    image = urljoin(url, meta.image) if meta and meta.image else ""
    return text[: settings["article_chars"]], image


def image_ok(url, settings):
    """True if the URL is https and really serves an image, so the email never shows a broken box."""
    if not url.startswith("https://"):
        return False
    try:
        with requests.get(url, stream=True, timeout=settings["article_timeout"],
                          headers={"User-Agent": settings["user_agent"]}) as resp:
            return resp.ok and resp.headers.get("Content-Type", "").startswith("image/")
    except Exception:
        return False


def is_google_news(url):
    return urlsplit(url).netloc.endswith("news.google.com")


def enrich_story(story, items, settings):
    """Resolve Google News links, fetch the best article's text, and pick a working image."""
    for link in story["links"]:
        if is_google_news(link["url"]):
            link["url"] = decode_google_news(link["url"], settings) or link["url"]
    # A link still pointing at Google News (or a TLDR issue page) is a last resort.
    direct = [l for l in story["links"] if not is_google_news(l["url"]) and "tldr.tech" not in l["url"]]
    story["url"] = (direct or story["links"])[0]["url"]

    article, og_image = None, ""
    for link in direct[:2]:
        try:
            text, og_image = fetch_article(link["url"], settings)
        except Exception as e:
            log.warning("article fetch failed for %s (%s)", link["url"], type(e).__name__)
            continue
        if len(text) >= 300:
            article = {"source": link["source"], "url": link["url"], "text": text}
            story["url"] = link["url"]
            break
    story["article"] = article

    candidates = [items[i]["image"] for i in story["ids"] if items[i]["image"]] + [og_image]
    story["image"] = next((u for u in candidates if u and image_ok(u, settings)), "")
    return story


def build_summary_prompt(stories, items):
    blocks = []
    for n, story in enumerate(stories, 1):
        lines = [f"=== Story {n} ===", f"Headline: {story['headline']}",
                 "Sources: " + ", ".join(dict.fromkeys(l["source"] for l in story["links"]))]
        for i in story["ids"]:
            snippet = clean_text(items[i]["summary"], items[i]["snippet_chars"])
            lines.append(f"Feed item ({items[i]['source']}): {items[i]['title']}" + (f" | {snippet}" if snippet else ""))
        if story["article"]:
            lines.append(f"ARTICLE TEXT ({story['article']['source']}):\n{story['article']['text']}")
        else:
            lines.append("ARTICLE TEXT: unavailable (use only the headline and feed items above)")
        blocks.append("\n".join(lines))
    return SUMMARY_PROMPT.format(stories="\n\n".join(blocks))


def parse_summaries(content, n_stories):
    data = json.loads(content)
    summaries = {}
    for s in data.get("stories", []):
        n, text = s.get("n"), (s.get("summary") or "").strip()
        if isinstance(n, int) and 1 <= n <= n_stories and text:
            summaries[n] = text
    if not summaries:
        raise ValueError("model returned no usable summaries")
    return summaries


def summarize(items, settings):
    """Pass 1 picks stories, then articles are fetched, then pass 2 writes paragraphs; all under a hard cap.

    If anything after pass 1 fails or the cap hits, the pass-1 digest (short summaries) is still used.
    """
    cap = settings["llm_step_cap"]
    result = {}

    def run():
        # Stop a few seconds early so the chain normally ends on its own, before the watchdog.
        deadline = time.monotonic() + cap - 5
        try:
            digest = run_llm_chain(build_prompt(items, settings), lambda c: parse_digest(c, items), settings,
                                   deadline, "pass 1", count=story_count,
                                   want=min(settings["min_stories"], len(items)))
        except Exception as e:
            result["error"] = e
            return
        result["digest"] = digest
        try:
            full = copy.deepcopy(digest)
            stories = [s for section in full["sections"] for s in section["stories"]]
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(lambda s: enrich_story(s, items, settings), stories))
            log.info("articles: fetched %d/%d, images %d/%d in %.0fs",
                     sum(1 for s in stories if s["article"]), len(stories),
                     sum(1 for s in stories if s["image"]), len(stories), time.monotonic() - started)
            result["digest"] = full  # links resolved and images found, even if pass 2 fails
            summaries = run_llm_chain(build_summary_prompt(stories, items), lambda c: parse_summaries(c, len(stories)),
                                      settings, deadline, "pass 2", final_try=False, count=len, want=len(stories))
            final = copy.deepcopy(full)
            for n, story in enumerate((s for section in final["sections"] for s in section["stories"]), 1):
                story["summary"] = summaries.get(n, story["summary"])
            result["digest"] = final
        except Exception as e:
            log.error("paragraph summaries failed, using short summaries (%s)", describe_error(e))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(cap)
    if worker.is_alive():
        if "digest" in result:
            log.error("LLM step hit the %ds hard cap; using what was ready", cap)
            return result["digest"]
        raise TimeoutError(f"LLM step hit the {cap}s hard cap")
    if "error" in result:
        raise result["error"]
    return result["digest"]


def fallback_digest(items):
    """Raw headlines grouped by source, used when the LLM step fails."""
    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(
            {"headline": item["title"], "summary": "", "url": item["link"], "links": [], "image": ""}
        )
    return {
        "tldr": "",
        "note": "The AI summary failed today, so here are the raw headlines grouped by source.",
        "sections": [{"name": name, "stories": stories} for name, stories in by_source.items()],
    }


SANS = "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SERIF = "ui-serif,'New York',Charter,Georgia,'Times New Roman',serif"

# Light colors are inline; the <style> block swaps them for dark mode (iCloud Mail / Apple Mail honor it).
DARK_CSS = """
:root { color-scheme: light dark; supported-color-schemes: light dark; }
@media (prefers-color-scheme: dark) {
  .bg { background-color: #1c1c1e !important; }
  .t1 { color: #f5f5f7 !important; }
  .t2 { color: #c7c7cc !important; }
  .t3 { color: #98989d !important; }
  .red { color: #ff375f !important; }
  .rule { border-color: #3a3a3c !important; }
  .rule-strong { border-color: #636366 !important; }
  .note { background-color: #3a2e05 !important; color: #ffd60a !important; }
}
@media (max-width: 480px) {
  .px { padding-left: 20px !important; padding-right: 20px !important; }
  .title { font-size: 32px !important; }
  .thumb { width: 76px !important; height: 76px !important; }
}
"""


def render_html(digest, title, heading, date_label):
    e = html.escape
    rows = []

    def row(content, pad="0 0 0 0", cls="px"):
        rows.append(f'<tr><td class="{cls}" style="padding:{pad};">{content}</td></tr>')

    def primary(story):
        """The link the headline points to (pass 2 may have switched to another source's article)."""
        return next((l for l in story["links"] if l["url"] == story["url"]), story["links"][0])

    def kicker(story):
        if not story["links"]:
            return ""
        return (f'<div class="t3" style="font-family:{SANS};font-size:13px;font-weight:600;letter-spacing:0.01em;'
                f'color:#6e6e73;margin:0 0 6px;">{e(primary(story)["source"])}</div>')

    def more_coverage(story):
        if not story["links"]:
            return ""
        main = primary(story)["source"]
        others = list({l["source"]: l for l in story["links"] if l["source"] != main}.values())
        if not others:
            return ""
        links = " &middot; ".join(
            f'<a href="{e(l["url"])}" class="t3" style="color:#6e6e73;text-decoration:underline;">{e(l["source"])}</a>'
            for l in others
        )
        return (f'<div class="t3" style="font-family:{SANS};font-size:13px;line-height:1.5;color:#6e6e73;'
                f'margin-top:10px;">Also covered by {links}</div>')

    def headline_link(story, size, weight="700"):
        return (f'<a href="{e(story["url"])}" class="t1" style="font-family:{SERIF};font-size:{size}px;'
                f'font-weight:{weight};line-height:1.25;color:#1d1d1f;text-decoration:none;">{e(story["headline"])}</a>')

    def summary_div(story, color="#3a3a3c", font=SERIF, size=16):
        if not story["summary"]:
            return ""
        return (f'<div class="t2" style="font-family:{font};font-size:{size}px;line-height:1.5;color:{color};'
                f'margin-top:6px;">{e(story["summary"])}</div>')

    def divider(strong=False):
        cls, width, color = ("rule-strong", 3, "#d2d2d7") if strong else ("rule", 1, "#e5e5ea")
        return (f'<tr><td class="px" style="padding:0 24px;"><div class="{cls}" style="border-top:{width}px solid '
                f'{color};font-size:0;line-height:0;">&nbsp;</div></td></tr>')

    # Header: date kicker, big title, the day in brief.
    row(f'<div class="t3" style="font-family:{SANS};font-size:13px;font-weight:700;letter-spacing:0.06em;'
        f'text-transform:uppercase;color:#6e6e73;">{e(date_label)}</div>'
        f'<div class="t1 title" style="font-family:{SANS};font-size:36px;font-weight:800;line-height:1.08;'
        f'letter-spacing:-0.02em;color:#1d1d1f;margin-top:4px;">{e(heading)}</div>', "32px 24px 18px")
    if digest["tldr"]:
        row(f'<div class="t2" style="font-family:{SERIF};font-size:17px;line-height:1.5;color:#3a3a3c;">'
            f'{e(digest["tldr"])}</div>', "0 24px 22px")
    if digest["note"]:
        row(f'<div class="note" style="background-color:#fff4d6;border-radius:8px;padding:12px 14px;font-family:{SANS};'
            f'font-size:14px;line-height:1.5;color:#7a4f00;">{e(digest["note"])}</div>', "0 24px 22px")

    for s_idx, section in enumerate(digest["sections"]):
        top = s_idx == 0 and section["name"] == "Top stories"
        rows.append(divider(strong=True))
        color, cls = ("#d70015", "red") if top else ("#1d1d1f", "t1")
        row(f'<div class="{cls}" style="font-family:{SANS};font-size:14px;font-weight:800;letter-spacing:0.16em;'
            f'text-transform:uppercase;color:{color};">{e(section["name"])}</div>', "14px 24px 14px")

        for i, story in enumerate(section["stories"]):
            rows.append(divider())
            if top and i == 0:
                # Featured story: big image, large serif headline, sans summary.
                img = (f'<a href="{e(story["url"])}"><img src="{e(story["image"])}" width="552" alt="" '
                       f'style="display:block;width:100%;max-width:552px;height:auto;border:0;border-radius:6px;'
                       f'margin-bottom:14px;"></a>') if story["image"] else ""
                row(img + kicker(story) + headline_link(story, 26)
                    + summary_div(story, color="#6e6e73", font=SANS, size=16).replace('class="t2"', 'class="t3"')
                    + more_coverage(story), "18px 24px 20px")
            elif top:
                # Top stories: bold serif lead-in running into lighter text, like a news brief.
                body = (f'<a href="{e(story["url"])}" class="t1" style="font-family:{SERIF};font-size:19px;'
                        f'font-weight:700;line-height:1.42;color:#1d1d1f;text-decoration:none;">{e(story["headline"])}.</a>')
                if story["summary"]:
                    body += (f' <span class="t3" style="font-family:{SERIF};font-size:19px;line-height:1.42;'
                             f'color:#6e6e73;">{e(story["summary"])}</span>')
                row(kicker(story) + f'<div style="line-height:1.42;">{body}</div>' + more_coverage(story),
                    "16px 24px 18px")
            else:
                # Section list: headline with a thumbnail on the right, paragraph below.
                thumb = ""
                if story["image"]:
                    thumb = (f'<td width="88" valign="top" style="padding-left:14px;"><a href="{e(story["url"])}">'
                             f'<img class="thumb" src="{e(story["image"])}" width="88" height="88" alt="" '
                             f'style="display:block;width:88px;height:88px;object-fit:cover;border:0;border-radius:6px;">'
                             f'</a></td>')
                top_row = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                           f'style="table-layout:fixed;"><tr>'
                           f'<td valign="top">{kicker(story)}{headline_link(story, 20)}</td>{thumb}</tr></table>')
                row(top_row + summary_div(story) + more_coverage(story), "16px 24px 18px")
    rows.append(divider(strong=True))
    row(f'<div class="t3" style="font-family:{SANS};font-size:12px;line-height:1.5;color:#6e6e73;">'
        f'Picked and summarized by AI from the day\'s feeds. Tap a headline to read the full story.</div>',
        "14px 24px 32px")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{e(title)}</title><style>{DARK_CSS}</style></head>
<body class="bg" style="margin:0;padding:0;background-color:#ffffff;-webkit-text-size-adjust:100%;word-wrap:break-word;overflow-wrap:break-word;">
<table role="presentation" class="bg" width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;table-layout:fixed;">
{chr(10).join(rows)}
</table>
</td></tr></table>
</body></html>
"""


def render_text(digest, title):
    lines = [title, ""]
    if digest["note"]:
        lines += [digest["note"], ""]
    if digest["tldr"]:
        lines += [f"TL;DR: {digest['tldr']}", ""]
    for section in digest["sections"]:
        lines += [f"== {section['name']} ==", ""]
        for story in section["stories"]:
            lines.append(f"* {story['headline']}")
            if story["summary"]:
                lines.append(f"  {story['summary']}")
            for link in story["links"] or [{"source": "Link", "url": story["url"]}]:
                lines.append(f"  {link['source']}: {link['url']}")
            lines.append("")
    return "\n".join(lines)


def send_email(subject, text_body, html_body, email_config):
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((email_config["from_name"], os.environ.get("EMAIL_FROM") or user))
    msg["To"] = formataddr((email_config["to_name"], os.environ["EMAIL_TO"]))
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    port = int(os.environ.get("SMTP_PORT") or 587)
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(user, os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)


def main():
    parser = argparse.ArgumentParser(description="Daily AI news digest")
    parser.add_argument("--dry-run", action="store_true", help="save digest.html instead of sending")
    args = parser.parse_args()

    load_dotenv()
    config = load_config()
    settings = config["settings"]
    results = fetch_all(config)
    for name, items in results.items():
        log.info("%s: %d items", name, len(items))

    all_items = [item for items in results.values() for item in items]
    unique, dropped = dedupe(all_items)
    log.info("dedupe: %d -> %d items", len(all_items), len(unique))
    if not unique:
        log.warning("no items at all; nothing to send")
        return

    try:
        digest = summarize(unique, settings)
    except Exception as e:
        log.error("LLM summary failed, sending raw headlines instead (%s)", describe_error(e))
        digest = fallback_digest(unique)

    now = datetime.now(ZoneInfo(settings["timezone"]))
    date_label = f"{now:%A, %B} {now.day}"
    email_config = config["email"]
    subject = f"{email_config['subject_prefix']} — {date_label}"
    html_body = render_html(digest, subject, email_config["subject_prefix"], date_label)
    text_body = render_text(digest, subject)

    if args.dry_run:
        out = Path(__file__).parent / "digest.html"
        out.write_text(html_body)
        print(text_body)
        log.info("dry run: saved %s (subject: %s)", out, subject)
    else:
        try:
            send_email(subject, text_body, html_body, email_config)
        except Exception as e:
            log.error("sending email failed: %s", e)
            raise SystemExit(1)
        log.info("sent: %s", subject)


if __name__ == "__main__":
    main()
