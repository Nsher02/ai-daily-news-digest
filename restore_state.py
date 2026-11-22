"""Restore the newest digest state artifact for the current repository branch."""

import io
import json
import os
import subprocess
import zipfile

from state_crypto import STATE_FILES, MAX_FILE_BYTES, MAX_STATE_BYTES, cipher, decode_files, decrypt_bundle, validate_files
from pathlib import Path

DELIVERY_WORKFLOW = ".github/workflows/daily-digest.yml"


def artifact_inventory(repo):
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"repos/{repo}/actions/artifacts?per_page=100"],
        check=True, capture_output=True,
    )
    return [artifact for page in json.loads(result.stdout) for artifact in page["artifacts"]]


def trusted_run(run, repo, branch):
    return (
        run.get("path") in {DELIVERY_WORKFLOW, ".github/workflows/state-maintenance.yml"}
        and run.get("event") in {"schedule", "workflow_dispatch"}
        and (run.get("path") == DELIVERY_WORKFLOW or run.get("event") == "workflow_dispatch")
        and run.get("head_branch") == branch
        and (run.get("repository") or {}).get("full_name") == repo
        and (run.get("head_repository") or {}).get("full_name") == repo
    )


def archive_files(raw, repo, branch, allow_legacy=False):
    if len(raw) > MAX_STATE_BYTES * 2:
        raise ValueError("State archive exceeds the size limit.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if "state.enc" in names:
            if names != ["state.enc"]:
                raise ValueError("Encrypted state archive must contain only state.enc.")
            info = archive.getinfo("state.enc")
            if info.file_size > MAX_STATE_BYTES * 2:
                raise ValueError("Encrypted member exceeds the size limit.")
            return decode_files(decrypt_bundle(archive.read(info), repo, branch))
        if not allow_legacy:
            raise ValueError("Plaintext recovery state requires private migration before delivery.")
        contents = {}
        for info in archive.infolist():
            if info.filename in STATE_FILES:
                if info.filename in contents or info.file_size > MAX_FILE_BYTES:
                    raise ValueError("Invalid legacy state member.")
                contents[info.filename] = archive.read(info)
        return validate_files(contents)


def restore(directory, repo, branch, allow_legacy=False):
    # Validate the key even on the first run; missing keys must stop before email preparation.
    cipher()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = [artifact for artifact in artifact_inventory(repo)
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
            checked_runs[run_id] = trusted_run(run, repo, branch)
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
    contents = archive_files(response.stdout, repo, branch, allow_legacy=allow_legacy)
    # Authenticate and validate every member before touching any existing state.
    for name, raw in contents.items():
        target = directory / name
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(target)
    print(f"Restored digest state artifact {latest['id']}.")


if __name__ == "__main__":
    restore(".digest-state", os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_NAME"])
