"""Decide whether a scheduled run should send today's digest.

GitHub's cron runs in UTC and can start late, so the workflow fires several times
each morning and this check lets through only the first run inside the local send
window. Manual runs never call this.
"""

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


def counts_as_sent(run, today):
    """A run blocks the morning send if it emailed today's digest, unless it was a manual run before the window."""
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
        runs.append({"id": run["id"], "event": run["event"], "started": run.get("run_started_at") or run["created_at"], "markers": markers})
    return runs


def main():
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
