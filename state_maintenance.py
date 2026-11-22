"""No-mail private migration and verified cleanup of plaintext state artifacts."""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from restore_state import archive_files, artifact_inventory, restore, trusted_run
from state_crypto import decode_files, decrypt_bundle, encode_files, encrypt_bundle, seal_directory

MAINTENANCE_PATH = '.github/workflows/state-maintenance.yml'


def api(path, method='GET', binary=False):
    response = subprocess.run(['gh', 'api', '--method', method, path], check=True, capture_output=True)
    return response.stdout if binary else (json.loads(response.stdout) if response.stdout else None)


def private_idle_repository(repo, current_run=None):
    if not api(f'repos/{repo}').get('private'):
        raise ValueError('Migration and cleanup require the repository to remain private.')
    for workflow in ['daily-digest.yml', 'state-maintenance.yml']:
        # Paginate so a queued older attempt is never hidden by recent runs.
        result = subprocess.run(['gh', 'api', '--paginate', '--slurp',
                                 f'repos/{repo}/actions/workflows/{workflow}/runs?per_page=100'],
                                check=True, capture_output=True)
        for page in json.loads(result.stdout):
            if any(r['status'] != 'completed' and str(r['id']) != str(current_run)
                   for r in page['workflow_runs']):
                raise ValueError('Wait for active or queued delivery/maintenance runs before cleanup.')


def download(repo, artifact):
    return api(f"repos/{repo}/actions/artifacts/{artifact['id']}/zip", binary=True)


def verify_origin(repo, branch, artifact, cache):
    run_id = artifact.get('workflow_run', {}).get('id')
    if type(run_id) is not int or run_id <= 0:
        raise ValueError('Artifact has no valid producing run.')
    if run_id not in cache:
        cache[run_id] = api(f'repos/{repo}/actions/runs/{run_id}')
    if not trusted_run(cache[run_id], repo, branch):
        raise ValueError('Artifact was not produced by a trusted delivery or maintenance run.')
    return cache[run_id]


def legacy_inventory(artifacts):
    return [a for a in artifacts if a['name'].startswith('digest-state-')
            and not a['name'].startswith('digest-state-encrypted-') and not a['expired']]


def migrate(repo, branch, output):
    private_idle_repository(repo, os.environ.get('GITHUB_RUN_ID'))
    artifacts = artifact_inventory(repo)
    old = legacy_inventory(artifacts)
    archives, metadata, cache = {}, [], {}
    for artifact in old:
        verify_origin(repo, branch, artifact, cache)
        raw = download(repo, artifact)
        archive_files(raw, repo, branch, allow_legacy=True)
        key = str(artifact['id'])
        archives[key] = base64.b64encode(raw).decode('ascii')
        metadata.append({'id': artifact['id'], 'name': artifact['name'],
                         'sha256': hashlib.sha256(raw).hexdigest()})
    output = Path(output)
    with tempfile.TemporaryDirectory() as temporary:
        restore(temporary, repo, branch, allow_legacy=True)
        files = {p.name: p.read_bytes() for p in Path(temporary).glob('*.json')}
        # Require an actual preserved edition, never an empty reset, before migration.
        seed = encode_files(files)
        seal_directory(temporary, output / 'state' / 'state.enc', repo, branch)
        payload = {'archives': archives, 'artifacts': metadata, 'seed': seed}
        backup = encrypt_bundle(payload, repo, branch, purpose='legacy-backup')
        # Authenticate a local round-trip before making either upload available.
        if decrypt_bundle(backup, repo, branch, purpose='legacy-backup') != payload:
            raise ValueError('Encrypted backup verification failed.')
        target = output / 'backup' / 'legacy-backup.enc'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(backup)
    print(f'Encrypted migration prepared for {len(old)} plaintext artifacts. No mail was sent.')


def cleanup(repo, branch, run_id, delete=False):
    private_idle_repository(repo)
    inventory = artifact_inventory(repo)
    candidates = [a for a in inventory if a.get('workflow_run', {}).get('id') == run_id and not a['expired']]
    backups = [a for a in candidates if a['name'].startswith('digest-legacy-encrypted-backup-')]
    states = [a for a in candidates if a['name'].startswith('digest-state-encrypted-migrated-')]
    if not backups or not states:
        raise ValueError('Both uploaded encrypted migration artifacts are required before cleanup.')
    backup_artifact, state_artifact = max(backups, key=lambda a:a['id']), max(states, key=lambda a:a['id'])
    cache = {}
    run = verify_origin(repo, branch, backup_artifact, cache)
    verify_origin(repo, branch, state_artifact, cache)
    if (run.get('path') != MAINTENANCE_PATH or run.get('status') != 'completed'
            or run.get('conclusion') != 'success'):
        raise ValueError('The trusted no-mail migration run must complete successfully first.')
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(download(repo, backup_artifact))) as archive:
        if archive.namelist() != ['legacy-backup.enc'] or archive.getinfo('legacy-backup.enc').file_size > 128_000_000:
            raise ValueError('Invalid encrypted backup archive.')
        backup = decrypt_bundle(archive.read('legacy-backup.enc'), repo, branch, purpose='legacy-backup')
    seed = archive_files(download(repo, state_artifact), repo, branch)
    if seed != decode_files(backup['seed']):
        raise ValueError('The uploaded encrypted state does not match the protected migration snapshot.')
    saved = {str(a['id']): a for a in backup['artifacts']}
    plan = legacy_inventory(inventory)
    # Verify EVERY deletion against the uploaded/decrypted original bytes first.
    for artifact in plan:
        verify_origin(repo, branch, artifact, cache)
        key = str(artifact['id'])
        if key not in saved or saved[key]['name'] != artifact['name'] or key not in backup['archives']:
            raise ValueError('A plaintext artifact is not covered by this encrypted backup. Migrate again.')
        original = base64.b64decode(backup['archives'][key], validate=True)
        if hashlib.sha256(original).hexdigest() != saved[key]['sha256'] or download(repo, artifact) != original:
            raise ValueError('An artifact does not match its verified encrypted backup.')
    if not delete:
        print('Verified cleanup plan; plaintext artifact IDs: ' + ', '.join(str(a['id']) for a in plan))
        return len(plan)
    private_idle_repository(repo)
    if {a['id'] for a in legacy_inventory(artifact_inventory(repo))} != {a['id'] for a in plan}:
        raise ValueError('Plaintext inventory changed during verification. Repeat migration/verification.')
    for artifact in plan:
        api(f"repos/{repo}/actions/artifacts/{artifact['id']}", method='DELETE')
        print(f"Deleted verified plaintext artifact {artifact['id']}.")
    remaining = legacy_inventory(artifact_inventory(repo))
    if remaining:
        raise ValueError('Plaintext state artifacts remain; keep the repository private and review them.')
    print(f'Cleanup complete: {len(plan)} plaintext artifacts removed; runs and receipts retained.')
    return len(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['migrate', 'cleanup'])
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--branch', default=os.environ.get('GITHUB_REF_NAME', 'main'))
    parser.add_argument('--output-directory', default='.digest-artifacts/migration')
    parser.add_argument('--run-id', type=int)
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    if not args.repo or args.branch != 'main':
        parser.error('Specify the repository and main branch.')
    if args.operation == 'migrate':
        migrate(args.repo, args.branch, args.output_directory)
    elif not args.run_id:
        parser.error('Cleanup requires the successful migration --run-id.')
    else:
        cleanup(args.repo, args.branch, args.run_id, args.delete)


if __name__ == '__main__':
    main()
