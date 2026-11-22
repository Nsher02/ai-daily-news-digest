"""Authenticated encryption for delivery state; never serialize or print credentials."""

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

STATE_FILES = {"history.json", "prepared.json", "quality.json"}
MAX_FILE_BYTES = 2_000_000
MAX_STATE_BYTES = 8_000_000
MAX_BACKUP_BYTES = 64_000_000


def cipher():
    try:
        return Fernet(os.environ.get("DIGEST_STATE_KEY", "").encode("ascii"))
    except (ValueError, UnicodeError):
        raise ValueError("Configure DIGEST_STATE_KEY with a generated Fernet key.") from None


def encrypt_bundle(payload, repo, branch, purpose="state"):
    envelope = {"version": 1, "repository": repo, "branch": branch,
                "purpose": purpose, "payload": payload}
    raw = json.dumps(envelope, separators=(",", ":")).encode()
    limit = MAX_STATE_BYTES if purpose == "state" else MAX_BACKUP_BYTES
    if len(raw) > limit:
        raise ValueError("Bundle exceeds the encryption size limit.")
    return cipher().encrypt(raw)


def decrypt_bundle(token, repo, branch, purpose="state"):
    limit = MAX_STATE_BYTES if purpose == "state" else MAX_BACKUP_BYTES
    if len(token) > limit * 2:
        raise ValueError("Encrypted bundle exceeds the size limit.")
    try:
        raw = cipher().decrypt(token)
    except InvalidToken:
        raise ValueError("State authentication failed; preserve the key and recovery artifacts.") from None
    if len(raw) > limit:
        raise ValueError("Decrypted bundle exceeds the size limit.")
    envelope = json.loads(raw)
    if (not isinstance(envelope, dict) or envelope.get("version") != 1
            or envelope.get("repository") != repo or envelope.get("branch") != branch
            or envelope.get("purpose") != purpose):
        raise ValueError("State bundle context does not match this operation.")
    return envelope.get("payload")


def validate_files(files):
    if not isinstance(files, dict) or "prepared.json" not in files or not set(files) <= STATE_FILES:
        raise ValueError("State bundle has an invalid file inventory.")
    if sum(len(raw) for raw in files.values()) > MAX_STATE_BYTES:
        raise ValueError("State exceeds the size limit.")
    for name, raw in files.items():
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("State member exceeds the size limit.")
        value = json.loads(raw)
        if name == "prepared.json" and not isinstance(value, dict):
            raise ValueError("Prepared state must be an object.")
    return files


def encode_files(files):
    validate_files(files)
    return {name: base64.b64encode(raw).decode("ascii") for name, raw in files.items()}


def decode_files(payload):
    if not isinstance(payload, dict) or not set(payload) <= STATE_FILES:
        raise ValueError("Invalid encrypted state inventory.")
    try:
        files = {name: base64.b64decode(value, validate=True) for name, value in payload.items()}
    except (ValueError, TypeError):
        raise ValueError("Invalid encrypted state member.") from None
    return validate_files(files)


def seal_directory(directory, output, repo, branch):
    root = Path(directory)
    files = {name: (root / name).read_bytes() for name in STATE_FILES if (root / name).is_file()}
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(encrypt_bundle(encode_files(files), repo, branch))
    temporary.replace(target)
    print("Encrypted delivery state saved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=".digest-state")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    seal_directory(args.directory, args.output, os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_NAME"])


if __name__ == "__main__":
    main()
