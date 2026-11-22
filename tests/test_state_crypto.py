"""Real encryption, fail-closed recovery and cleanup tests; no network or email."""
import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
import restore_state
import state_crypto as crypto
import state_maintenance as maintenance

REPO = 'owner/repo'
FILES = {'prepared.json': b'{"recipient":"private@example.com","html_body":"private fixture","delivery_status":"smtp_accepted"}',
         'history.json': b'{"version":1,"entries":[]}', 'quality.json': b'[]'}


def zipped(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return output.getvalue()


class KeyCase(unittest.TestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode()
        env = patch.dict(os.environ, {'DIGEST_STATE_KEY': self.key})
        env.start()
        self.addCleanup(env.stop)

    def encrypted(self, files=FILES):
        return crypto.encrypt_bundle(crypto.encode_files(files), REPO, 'main')

class EncryptionTests(KeyCase):
    def test_round_trip_preserves_every_byte_and_hides_personal_data(self):
        token = self.encrypted()
        for value in [b'private@example.com', b'private fixture', b'prepared.json']:
            self.assertNotIn(value, token)
        self.assertEqual(crypto.decode_files(crypto.decrypt_bundle(token, REPO, 'main')), FILES)
        self.assertNotEqual(token, self.encrypted())
        self.assertEqual(restore_state.archive_files(zipped({'state.enc': token}), REPO, 'main'), FILES)

    def test_wrong_key_tampering_context_and_purpose_fail_closed(self):
        token = self.encrypted()
        for repo, branch, purpose in [('other/repo', 'main', 'state'), (REPO,'feature','state'), (REPO,'main','legacy-backup')]:
            with self.subTest(repo=repo,branch=branch,purpose=purpose), self.assertRaises(ValueError):
                crypto.decrypt_bundle(token, repo, branch, purpose)
        with patch.dict(os.environ, {'DIGEST_STATE_KEY': Fernet.generate_key().decode()}), self.assertRaises(ValueError):
            crypto.decrypt_bundle(token, REPO, 'main')
        tampered = bytearray(token)
        tampered[len(tampered)//2] ^= 1
        with self.assertRaises(ValueError):
            crypto.decrypt_bundle(bytes(tampered), REPO, 'main')

    def test_missing_or_invalid_key_never_reaches_github(self):
        for key in ['', 'not-a-key', '☃']:
            with self.subTest(key=key), patch.dict(os.environ, {'DIGEST_STATE_KEY':key}), patch.object(restore_state.subprocess, 'run') as run:
                with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                    restore_state.restore(tmp, REPO, 'main')
                run.assert_not_called()

    def test_plaintext_requires_explicit_migration_and_mixed_archives_are_rejected(self):
        raw = zipped(FILES)
        with self.assertRaisesRegex(ValueError, 'migration'):
            restore_state.archive_files(raw, REPO, 'main')
        self.assertEqual(restore_state.archive_files(raw, REPO, 'main', allow_legacy=True), FILES)
        with self.assertRaises(ValueError):
            restore_state.archive_files(zipped(dict(FILES, **{'state.enc':self.encrypted()})), REPO, 'main')

    def test_invalid_member_and_corrupt_json_do_not_overwrite_state(self):
        for payload in [dict(crypto.encode_files(FILES), **{'../escape.json':'e30='}),
                        {'prepared.json':base64.b64encode(b'not json').decode()}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                restore_state.archive_files(zipped({'state.enc':crypto.encrypt_bundle(payload, REPO, 'main')}), REPO, 'main')
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
            target=Path(tmp)/'prepared.json';target.write_bytes(b'original')
            artifact={'id':1,'name':'digest-state-encrypted-final-1','expired':False,'workflow_run':{'id':10,'head_branch':'main'}}
            origin={'path':restore_state.DELIVERY_WORKFLOW,'event':'schedule','head_branch':'main',
                    'repository':{'full_name':REPO},'head_repository':{'full_name':REPO}}
            run.side_effect=[Mock(stdout=json.dumps([{'artifacts':[artifact]}]).encode()),Mock(stdout=json.dumps(origin).encode()),Mock(stdout=zipped({'state.enc':b'broken'}))]
            with self.assertRaises(ValueError):restore_state.restore(tmp,REPO,'main')
            self.assertEqual(target.read_bytes(),b'original')

    def test_sealed_staging_contains_only_encrypted_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state';state.mkdir()
            for name,raw in FILES.items():(state/name).write_bytes(raw)
            output=root/'upload'/'state.enc'
            crypto.seal_directory(state,output,REPO,'main')
            self.assertEqual([p.name for p in output.parent.iterdir()],['state.enc'])
            self.assertEqual(crypto.decode_files(crypto.decrypt_bundle(output.read_bytes(),REPO,'main')),FILES)


class CleanupTests(KeyCase):
    def context(self, changed=False, uncovered=False):
        import hashlib
        raw=zipped(FILES)
        old={'id':1,'name':'digest-state-final-old','expired':False,'workflow_run':{'id':10,'head_branch':'main'}}
        state={'id':2,'name':'digest-state-encrypted-migrated-20-1','expired':False,'workflow_run':{'id':20,'head_branch':'main'}}
        backup={'id':3,'name':'digest-legacy-encrypted-backup-20-1','expired':False,'workflow_run':{'id':20,'head_branch':'main'}}
        payload={'archives':{'1':base64.b64encode(raw).decode()},'artifacts':[{'id':1,'name':old['name'],'sha256':hashlib.sha256(raw).hexdigest()}],'seed':crypto.encode_files(FILES)}
        archives={1:b'changed' if changed else raw,2:zipped({'state.enc':self.encrypted()}),3:zipped({'legacy-backup.enc':crypto.encrypt_bundle(payload,REPO,'main','legacy-backup')})}
        inventory=[old,state,backup]
        if uncovered:inventory.append(dict(old,id=4))
        run={'path':maintenance.MAINTENANCE_PATH,'event':'workflow_dispatch','head_branch':'main','status':'completed','conclusion':'success','repository':{'full_name':REPO},'head_repository':{'full_name':REPO}}
        return inventory,archives,run

    def test_cleanup_deletes_only_backed_up_plaintext_and_keeps_runs(self):
        inventory,archives,run=self.context()
        deleted=[]
        def api(path,method='GET',binary=False):
            if method=='DELETE':deleted.append(path);return None
            return run
        with patch.object(maintenance,'private_idle_repository'), patch.object(maintenance,'artifact_inventory',side_effect=[inventory,inventory,inventory[1:]]), patch.object(maintenance,'download',side_effect=lambda repo,a:archives[a['id']]), patch.object(maintenance,'api',side_effect=api):
            self.assertEqual(maintenance.cleanup(REPO,'main',20,delete=True),1)
        self.assertEqual(deleted,[f'repos/{REPO}/actions/artifacts/1'])

    def test_changed_or_uncovered_artifacts_abort_before_any_deletion(self):
        for changed,uncovered in [(True,False),(False,True)]:
            inventory,archives,run=self.context(changed,uncovered)
            with self.subTest(changed=changed,uncovered=uncovered), patch.object(maintenance,'private_idle_repository'), patch.object(maintenance,'artifact_inventory',return_value=inventory), patch.object(maintenance,'download',side_effect=lambda repo,a:archives[a['id']]), patch.object(maintenance,'api',return_value=run) as api:
                with self.assertRaises(ValueError):maintenance.cleanup(REPO,'main',20,delete=True)
                self.assertFalse(any(c.kwargs.get('method')=='DELETE' for c in api.call_args_list))

    def test_failed_migration_or_missing_backup_never_deletes(self):
        inventory,archives,run=self.context()
        run['conclusion']='failure'
        for records in [inventory,inventory[:2]]:
            with self.subTest(records=len(records)), patch.object(maintenance,'private_idle_repository'), patch.object(maintenance,'artifact_inventory',return_value=records), patch.object(maintenance,'api',return_value=run) as api:
                with self.assertRaises(ValueError):maintenance.cleanup(REPO,'main',20,delete=True)
                self.assertFalse(any(c.kwargs.get('method')=='DELETE' for c in api.call_args_list))

    def test_migration_encrypts_original_archive_and_exact_recovery_seed(self):
        inventory, archives, origin = self.context()
        def restore(directory, repo, branch, allow_legacy=False):
            self.assertTrue(allow_legacy)
            for name, raw in FILES.items():(Path(directory)/name).write_bytes(raw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(maintenance,'private_idle_repository'), patch.object(maintenance,'artifact_inventory',return_value=inventory), patch.object(maintenance,'download',side_effect=lambda repo,a:archives[a['id']]), patch.object(maintenance,'api',return_value=origin), patch.object(maintenance,'restore',side_effect=restore):
            maintenance.migrate(REPO,'main',tmp)
            seed = crypto.decode_files(crypto.decrypt_bundle((Path(tmp)/'state/state.enc').read_bytes(),REPO,'main'))
            backup = crypto.decrypt_bundle((Path(tmp)/'backup/legacy-backup.enc').read_bytes(),REPO,'main','legacy-backup')
            self.assertEqual(seed,FILES)
            self.assertEqual(crypto.decode_files(backup['seed']),FILES)
            self.assertEqual(base64.b64decode(backup['archives']['1']),archives[1])
            self.assertEqual(sorted(p.name for p in Path(tmp).rglob('*') if p.is_file()),['legacy-backup.enc','state.enc'])

    def test_public_repo_or_active_run_blocks_maintenance(self):
        with patch.object(maintenance,'api',return_value={'private':False}), self.assertRaises(ValueError):
            maintenance.private_idle_repository(REPO)
        with patch.object(maintenance,'api',return_value={'private':True}), patch.object(maintenance.subprocess,'run',return_value=Mock(stdout=json.dumps([{'workflow_runs':[{'id':10,'status':'in_progress'}]}]).encode())), self.assertRaises(ValueError):
            maintenance.private_idle_repository(REPO)
