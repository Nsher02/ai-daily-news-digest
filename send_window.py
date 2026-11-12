"""Decide whether a scheduled run should send today's digest.

Scheduled runs come from cron-job.org (workflow_dispatch with trigger=external-schedule)
and from GitHub's own cron as a backup, which runs in UTC and can start late or not at
all. This check lets through only the first scheduled run inside the local send window.
Plain manual runs always send.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")
WINDOW_START = time(7, 45)
WINDOW_END = time(10, 0)
MARKER = "SMTP accepted: "


def parse_time(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def is_scheduled(event, trigger):
    return event == "schedule" or (event == "workflow_dispatch" and trigger == "external-schedule")


def counts_as_sent(run, today):
    """A run blocks the morning send if it emailed today's digest, unless it was a manual run before the window.

    External-schedule runs are also workflow_dispatch, but they can only send inside the window.
    """
    if MARKER + today.isoformat() not in run["markers"]:
        return False
    started = parse_time(run["started"]).astimezone(TZ)
    return not (run["event"] == "workflow_dispatch" and started.date() == today and started.time() < WINDOW_START)


def decide(now, runs):
    """Return (send, reason) for a scheduled run at `now` given today's earlier runs."""
    local = now.astimezone(TZ)
    stamp = local.strftime("%H:%M %Z")
    if not WINDOW_START <= local.time() < WINDOW_END:
        return False, f"{stamp} is outside the 07:45-10:00 Chicago send window"
    sent = [run for run in runs if counts_as_sent(run, local.date())]
    if sent:
        return False, f"today's digest was already sent by run {sent[0]['id']} ({sent[0]['event']})"
    return True, f"{stamp} is inside the send window and nothing has been sent today"


def gh_json(path):
    out = subprocess.run(["gh", "api", "--paginate", "--slurp", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def recent_runs(repo, now, current_id):
    since = (now - timedelta(days=2)).date().isoformat()
    pages = gh_json(f"repos/{repo}/actions/workflows/daily-digest.yml/runs?created=%3E%3D{since}&per_page=100")
    runs = []
    for run in (r for page in pages for r in page["workflow_runs"]):
        if str(run["id"]) == current_id:
            continue
        jobs = gh_json(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=all&per_page=100")
        markers = {step["name"] for page in jobs for job in page["jobs"] for step in job.get("steps") or []
                   if step["conclusion"] == "success" and step["name"].startswith(MARKER)}
        runs.append({"id": run["id"], "event": run["event"], "started": run.get("run_started_at") or run["created_at"], "markers": markers, "status": run.get("status"), "conclusion": run.get("conclusion")})
    return runs


def compute_alert_id(kind, digest_date, extra=""):
    """Stable alert identifier for monitoring notifications; no recipient or transport is implied."""
    seed = "|".join(str(part) for part in [kind, digest_date, extra, "digest-monitor-v1"])
    return f"digest-alert-{kind}-{digest_date}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def degraded_quality(value):
    return str(value or "").lower() in {"raw_headlines", "pass_1", "partial_pass_2"}


def quality_streak(history, threshold=2):
    """Return info about a consecutive degraded-quality run streak, or None when healthy."""
    if threshold <= 0:
        return None
    seen = 0
    latest = None
    for entry in history or []:
        quality = entry.get("quality") if isinstance(entry, dict) else None
        if degraded_quality(quality):
            seen += 1
            latest = entry
        else:
            break
    if seen >= threshold:
        digest_date = str((latest or {}).get("digest_date") or (latest or {}).get("date") or "unknown")
        return {
            "status": "degraded_quality",
            "digest_date": digest_date,
            "count": seen,
            "threshold": threshold,
            "quality": (latest or {}).get("quality"),
            "alert_id": compute_alert_id("quality", digest_date, f"threshold={threshold}"),
        }
    return None


def missing_digest_alert(now, runs, today=None, threshold=None):
    """Return an actionable missing-digest alert or None when the digest is present or still in-flight."""
    now = now.astimezone(TZ)
    today = today or now.date()
    if now.time() < WINDOW_END:
        return None
    sent = [run for run in runs if counts_as_sent(run, today)]
    if sent:
        return None

    active = []
    for run in runs:
        started = parse_time(run.get("started") or run.get("created_at") or "1970-01-01T00:00:00Z")
        started_local = started.astimezone(TZ)
        if started_local.date() == today and (run.get("status") == "in_progress" or run.get("state") == "in_progress"):
            active.append(run)
    if active:
        return {"status": "pending_active_run", "digest_date": today.isoformat(), "alert_id": compute_alert_id("missing", today.isoformat(), "active-run")}

    failed = [run for run in runs if (run.get("event") == "schedule" or run.get("event") == "workflow_dispatch") and parse_time(run.get("started") or run.get("created_at") or "1970-01-01T00:00:00Z").astimezone(TZ).date() == today]
    if not failed:
        return {"status": "missing_digest", "digest_date": today.isoformat(), "alert_id": compute_alert_id("missing", today.isoformat(), "no-run")}
    return {"status": "missing_digest", "digest_date": today.isoformat(), "alert_id": compute_alert_id("missing", today.isoformat(), "no-receipt")}


def dedupe_alerts(alerts, seen=None):
    """Return only new alerts based on a stable alert-id set; used for review without repeated notifications."""
    seen = set(seen or [])
    unique = []
    for alert in alerts or []:
        alert_id = str((alert or {}).get("alert_id") or "")
        if not alert_id or alert_id in seen:
            continue
        seen.add(alert_id)
        unique.append(alert)
    return unique


def evaluate_monitor(now, runs=None, quality_history=None, threshold=2):
    """Evaluate the inactive monitoring state for one day without sending any notification."""
    runs = runs or []
    quality_history = quality_history or []
    alerts = []
    missing = missing_digest_alert(now, runs)
    if missing and missing["status"] != "pending_active_run":
        alerts.append(missing)
    streak = quality_streak(quality_history, threshold=threshold)
    if streak:
        alerts.append(streak)
    return {"missing_digest": missing, "degraded_quality": streak, "alerts": dedupe_alerts(alerts)}


def main():
    if not is_scheduled(os.environ.get("EVENT_NAME", ""), os.environ.get("TRIGGER") or "manual"):
        send, reason = True, "manual run, always sends"
    else:
        now = datetime.now(timezone.utc)
        send, reason = decide(now, recent_runs(os.environ["GITHUB_REPOSITORY"], now, os.environ.get("GITHUB_RUN_ID", "")))
    print(("Sending: " if send else "Skipping: ") + reason)
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        handle.write(f"skip={'false' if send else 'true'}\n")
    if not send and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(f"Digest skipped: {reason}.\n")


if __name__ == "__main__":
    sys.exit(main())
