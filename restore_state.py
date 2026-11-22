"""Restore the newest digest state artifact for the current repository branch."""

import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

STATE_FILES = {"history.json", "prepared.json", "quality.json"}
DELIVERY_WORKFLOW = ".github/workflows/daily-digest.yml"


def restore(directory, repo, branch):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repo}/actions/artifacts?per_page=100"],
        check=True, capture_output=True,
    )
    artifacts = [artifact for page in json.loads(result.stdout) for artifact in page["artifacts"]
                 if artifact["name"].startswith("digest-state-") and not artifact["expired"]
                 and artifact.get("workflow_run", {}).get("head_branch") == branch]
    if not artifacts:
        print("No previous digest state artifact. Starting with empty history.")
        return
    latest = None
    checked_runs = {}
    for artifact in sorted(artifacts, key=lambda artifact: artifact["id"], reverse=True):
        run_id = artifact.get("workflow_run", {}).get("id")
        if type(run_id) is not int or run_id <= 0:
            continue
        if run_id not in checked_runs:
            # Branch names and artifact names can be chosen by fork PRs. Verify
            # the authoritative run before trusting any recovered email content.
            run_response = subprocess.run(
                ["gh", "api", f"repos/{repo}/actions/runs/{run_id}"],
                check=True, capture_output=True,
            )
            run = json.loads(run_response.stdout)
            checked_runs[run_id] = (
                run.get("path") == DELIVERY_WORKFLOW
                and run.get("event") in {"schedule", "workflow_dispatch"}
                and run.get("head_branch") == branch
                and (run.get("repository") or {}).get("full_name") == repo
                and (run.get("head_repository") or {}).get("full_name") == repo
            )
        if checked_runs[run_id]:
            latest = artifact
            break
    if latest is None:
        print("No trusted delivery state artifact. Starting with empty history.")
        return
    response = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/artifacts/{latest['id']}/zip"],
        check=True, capture_output=True,
    )
    # Extract only expected basenames. Never use extractall on downloaded state.
    with zipfile.ZipFile(io.BytesIO(response.stdout)) as archive:
        contents = {}
        for name in archive.namelist():
            if name in STATE_FILES:
                raw = archive.read(name)
                json.loads(raw)
                contents[name] = raw
        if "prepared.json" not in contents:
            raise ValueError("digest state archive has no prepared edition")
        for name, raw in contents.items():
            target = directory / name
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(raw)
            temporary.replace(target)
    print(f"Restored digest state artifact {latest['id']}.")


if __name__ == "__main__":
    restore(".digest-state", os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_NAME"])
