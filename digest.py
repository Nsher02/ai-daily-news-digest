"""Daily CS & AI news digest."""

import argparse
import calendar
import html
import json
import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
import yaml
from dotenv import load_dotenv
from openai import OpenAI

CONFIG_PATH = Path(__file__).parent / "config.yaml"
LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_LLM_MODEL = "gemini-3.8-flash"
SECTIONS = ["Top stories", "AI models & labs", "Industry & business", "Research", "Software & computing"]

PROMPT = """You are editing a daily CS & AI news digest for a CS grad student / software engineer.

Below are today's items, each with a numeric ID. Pick the {max_stories} most important stories.
- Merge items that cover the same story into one story listing all their IDs.
- Skip promos, event ads, sponsored posts, listicles and fluff.
- Group stories into these sections, in this order (omit empty ones): {sections}.
- "Top stories" holds the 3-4 biggest stories of the day; don't repeat them in other sections.
- Write an original headline and a 1-2 sentence factual summary for each story.
- Some items are marked "(title only)". For those, summarize ONLY what the headline itself says (e.g. "HN discussion of …" / "Post about …").
- Never add details, causes, numbers or quotes that aren't in the item's title or snippet. If unsure, keep it short and say less.
- Write a 2-3 sentence "tldr" of the day.
- Use only IDs from the list. Do not include URLs.

Return ONLY JSON in this exact shape:
{{"tldr": "...", "sections": [{{"name": "...", "stories": [{{"ids": [1, 2], "headline": "...", "summary": "..."}}]}}]}}

Items:
{items}"""

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
        items.append({
            "source": feed["name"],
            "title": html.unescape(entry.get("title", "")).strip(),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", ""),
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


def summarize(items, settings):
    """Ask the LLM to pick and summarize top stories; attach real links by ID."""
    lines = []
    for i, item in enumerate(items):
        snippet = clean_text(item["summary"], 300)
        lines.append(f"[{i}] ({item['source']}) {item['title']}\n    {snippet or '(title only)'}")
    prompt = PROMPT.format(
        max_stories=settings["max_stories"],
        sections=", ".join(SECTIONS),
        items="\n".join(lines),
    )
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=LLM_BASE_URL, max_retries=5)
    resp = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=settings["llm_timeout"],
    )
    data = json.loads(resp.choices[0].message.content)

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
            })
        if stories:
            sections.append({"name": section.get("name", ""), "stories": stories})
    if not sections:
        raise ValueError("model returned no usable stories")
    return {"tldr": data.get("tldr", "").strip(), "note": "", "sections": sections}


def fallback_digest(items):
    """Raw headlines grouped by source, used when the LLM step fails."""
    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(
            {"headline": item["title"], "summary": "", "url": item["link"], "links": []}
        )
    return {
        "tldr": "",
        "note": "The AI summary failed today, so here are the raw headlines grouped by source.",
        "sections": [{"name": name, "stories": stories} for name, stories in by_source.items()],
    }


FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def render_html(digest, title, heading, date_label):
    e = html.escape
    rows = []
    if digest["note"]:
        rows.append(
            f'<tr><td style="padding:0 24px 20px;"><div style="background:#fef3c7;border-radius:6px;'
            f'padding:12px 14px;font-family:{FONT};font-size:14px;line-height:1.5;color:#78350f;">'
            f'{e(digest["note"])}</div></td></tr>'
        )
    if digest["tldr"]:
        rows.append(
            f'<tr><td style="padding:0 24px 20px;"><div style="background:#f3f4f6;border-radius:6px;'
            f'padding:14px 16px;font-family:{FONT};font-size:15px;line-height:1.55;color:#1f2937;">'
            f'<strong>TL;DR</strong> {e(digest["tldr"])}</div></td></tr>'
        )
    for section in digest["sections"]:
        rows.append(
            f'<tr><td style="padding:12px 24px 10px;font-family:{FONT};font-size:12px;font-weight:700;'
            f'letter-spacing:0.08em;text-transform:uppercase;color:#2563eb;'
            f'border-top:1px solid #e5e7eb;">{e(section["name"])}</td></tr>'
        )
        for story in section["stories"]:
            parts = [
                f'<a href="{e(story["url"])}" style="font-size:16px;font-weight:600;line-height:1.35;'
                f'color:#111827;text-decoration:none;">{e(story["headline"])}</a>'
            ]
            if story["summary"]:
                parts.append(
                    f'<div style="margin-top:4px;font-size:15px;line-height:1.5;color:#374151;">'
                    f'{e(story["summary"])}</div>'
                )
            if story["links"]:
                links = " &middot; ".join(
                    f'<a href="{e(l["url"])}" style="color:#2563eb;text-decoration:none;">{e(l["source"])}</a>'
                    for l in story["links"]
                )
                parts.append(f'<div style="margin-top:6px;font-size:13px;color:#6b7280;">{links}</div>')
            rows.append(f'<tr><td style="padding:0 24px 18px;font-family:{FONT};">{"".join(parts)}</td></tr>')

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:#f4f4f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:8px;">
<tr><td style="padding:28px 24px 18px;font-family:{FONT};">
<div style="font-size:22px;font-weight:700;color:#111827;">{e(heading)}</div>
<div style="margin-top:2px;font-size:14px;color:#6b7280;">{e(date_label)}</div>
</td></tr>
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
    parser = argparse.ArgumentParser(description="Daily CS & AI news digest")
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
        log.error("LLM summary failed, sending raw headlines instead (%s)", e)
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
