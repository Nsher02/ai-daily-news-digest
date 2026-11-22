"""Offline integration checks for the workflow's prepared-edition entry points."""

import copy
import io
import json
import os
import smtplib
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import digest
import restore_state
import send_window


class PreparedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = digest.load_config()
        self.config['settings'].update(story_history_path=str(self.root / 'history.json'),
                                       prepared_edition_path=str(self.root / 'prepared.json'),
                                       quality_history_path=str(self.root / 'quality.json'))
        self.item = dict(title='A public model release', source='Publisher', link='https://example.com/model',
                         summary='Original facts', snippet_chars=300, image='')
        self.edition = digest.fallback_digest([self.item])
        self.edition['quality'] = 'raw_headlines'
        self.env = {'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': '587', 'SMTP_USER': 'sender@example.com',
                    'SMTP_PASSWORD': 'offline-password', 'EMAIL_TO': 'reader@example.com',
                    'TRIGGER': 'external-schedule', 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_OUTPUT': str(self.root / 'output')}

    def run_main(self, *args):
        with patch('sys.argv', ['digest.py', *args]), patch.object(digest, 'load_dotenv'), patch.object(digest, 'load_config', return_value=copy.deepcopy(self.config)):
            digest.main()

    def prepare(self):
        with patch.object(digest, 'fetch_all', return_value={'Feed': [self.item]}), patch.object(digest, 'summarize', return_value=self.edition), patch.object(digest, 'send_email') as send:
            password = os.environ.pop('SMTP_PASSWORD', None)
            try:
                self.run_main('--prepare-only')
            finally:
                if password is not None:
                    os.environ['SMTP_PASSWORD'] = password
            send.assert_not_called()

    def test_prepare_send_and_accepted_retry_preserve_content_and_history(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.prepare()
            before = json.loads((self.root / 'prepared.json').read_text())
            self.assertEqual(before['delivery_status'], 'sending')
            self.assertFalse((self.root / 'history.json').exists())
            with patch.object(digest, 'fetch_all', side_effect=AssertionError('retry fetched feeds')), patch.object(digest, 'summarize', side_effect=AssertionError('retry called AI')), patch.object(digest.smtplib, 'SMTP') as smtp:
                self.run_main('--send-prepared')
                self.run_main('--send-prepared')
                submit = smtp.return_value.__enter__.return_value.send_message
                self.assertEqual(submit.call_count, 1)
                message = submit.call_args.args[0]
                self.assertEqual(message['Message-ID'], before['message_id'])
                self.assertEqual(message['Subject'], before['subject'])
            history = digest.load_story_history(path=self.root / 'history.json', settings=self.config['settings'])
            self.assertEqual(len(history), 1)
            self.assertEqual(digest.apply_story_history_filter([self.item], self.config['settings'], history), [])
            self.assertIn('outcome=sent', (self.root / 'output').read_text())
            self.assertEqual(json.loads((self.root / 'quality.json').read_text())[0]['quality'], 'raw_headlines')

    def test_old_reservation_blocks_next_runner_without_fetching_or_sending(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.prepare()
            os.environ['GITHUB_RUN_ID'] = '101'
            with patch.object(digest, 'fetch_all') as fetch, patch.object(digest, 'send_email') as send:
                with self.assertRaises(SystemExit):
                    self.run_main('--send-prepared')
                fetch.assert_not_called()
                send.assert_not_called()
            self.assertNotIn('outcome=sent', (self.root / 'output').read_text())

    def test_disconnect_during_submission_is_not_reported_as_accepted(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.prepare()
            with patch.object(digest.smtplib, 'SMTP') as smtp:
                smtp.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPServerDisconnected('connection lost')
                with self.assertRaises(SystemExit):
                    self.run_main('--send-prepared')
            saved = json.loads((self.root / 'prepared.json').read_text())
            self.assertEqual(saved['delivery_status'], 'unknown')
            self.assertFalse((self.root / 'history.json').exists())
            self.assertNotIn('outcome=sent', (self.root / 'output').read_text())

    def test_rejected_submission_can_retry_identical_prepared_content(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.prepare()
            before = json.loads((self.root / 'prepared.json').read_text())
            with patch.object(digest.smtplib, 'SMTP') as smtp:
                smtp.return_value.__enter__.return_value.send_message.side_effect = smtplib.SMTPDataError(550, b'rejected')
                with self.assertRaises(SystemExit):
                    self.run_main('--send-prepared')
            self.assertEqual(json.loads((self.root / 'prepared.json').read_text())['delivery_status'], 'failed')
            os.environ['GITHUB_RUN_ID'] = '101'
            with patch.object(digest.smtplib, 'SMTP') as smtp, patch.object(digest, 'fetch_all') as fetch:
                self.run_main('--send-prepared')
                fetch.assert_not_called()
                message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                self.assertEqual(message['Message-ID'], before['message_id'])
                self.assertEqual(message.get_body(preferencelist=('html',)).get_content().strip(), before['html_body'].strip())

    def test_missing_prepared_record_never_regenerates_during_send_phase(self):
        with patch.dict(os.environ, self.env, clear=True), patch.object(digest, 'fetch_all') as fetch:
            with self.assertRaises(ValueError):
                self.run_main('--send-prepared')
            fetch.assert_not_called()


class ArtifactRestoreTests(unittest.TestCase):
    @staticmethod
    def trusted_run(**changes):
        run = dict(path='.github/workflows/daily-digest.yml', event='schedule', head_branch='main',
                   repository={'full_name': 'owner/repo'}, head_repository={'full_name': 'owner/repo'})
        return dict(run, **changes)

    @staticmethod
    def artifact(artifact_id=1, run_id=10):
        return dict(id=artifact_id, name='digest-state-final-fixture', expired=False,
                    workflow_run=dict(id=run_id, head_branch='main'))

    @staticmethod
    def archive():
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('prepared.json', '{"delivery_status":"prepared"}')
        return payload.getvalue()

    def test_restore_rejects_untrusted_runs_before_downloading(self):
        for changes in [dict(event='pull_request'), dict(event='pull_request_target'),
                        dict(path='.github/workflows/tests.yml'), dict(head_branch='feature'),
                        dict(repository={'full_name': 'other/repo'}),
                        dict(head_repository={'full_name': 'attacker/repo'}),
                        dict(head_repository=None)]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
                run.side_effect = [Mock(stdout=json.dumps([{'artifacts': [self.artifact()]}]).encode()),
                                   Mock(stdout=json.dumps(self.trusted_run(**changes)).encode())]
                restore_state.restore(tmp, 'owner/repo', 'main')
                self.assertEqual(run.call_count, 2)
                self.assertFalse((Path(tmp) / 'prepared.json').exists())

    def test_restore_skips_forged_newest_artifact_and_accepts_failed_delivery_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
            run.side_effect = [Mock(stdout=json.dumps([{'artifacts': [self.artifact(2, 20), self.artifact()]}]).encode()),
                               Mock(stdout=json.dumps(self.trusted_run(event='pull_request')).encode()),
                               Mock(stdout=json.dumps(self.trusted_run(event='workflow_dispatch', conclusion='failure')).encode()),
                               Mock(stdout=self.archive())]
            restore_state.restore(tmp, 'owner/repo', 'main')
            self.assertIn('/1/zip', run.call_args.args[0][-1])
            self.assertTrue((Path(tmp) / 'prepared.json').exists())

    def test_run_lookup_failure_never_downloads_or_overwrites_existing_state(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
            state = Path(tmp) / 'prepared.json'
            state.write_text('{"existing":true}')
            run.side_effect = [Mock(stdout=json.dumps([{'artifacts': [self.artifact()]}]).encode()),
                               subprocess.CalledProcessError(1, 'gh')]
            with self.assertRaises(subprocess.CalledProcessError):
                restore_state.restore(tmp, 'owner/repo', 'main')
            self.assertEqual(state.read_text(), '{"existing":true}')
            self.assertEqual(run.call_count, 2)

    def test_missing_run_id_is_not_used_as_an_api_path(self):
        for run_id in [None, True, '../other', 0]:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
                run.return_value = Mock(stdout=json.dumps([{'artifacts': [self.artifact(run_id=run_id)]}]).encode())
                restore_state.restore(tmp, 'owner/repo', 'main')
                self.assertEqual(run.call_count, 1)

    def test_restore_uses_latest_matching_branch_and_expected_files(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as archive:
            archive.writestr('prepared.json', json.dumps({'delivery_status': 'prepared'}))
            archive.writestr('history.json', '[]')
            archive.writestr('../escape.json', '{}')
        artifacts = [{'id': i, 'name': name, 'expired': expired, 'workflow_run': {'id': 10, 'head_branch': branch}}
                     for i, name, expired, branch in [(1, 'digest-state-prepared-1', False, 'main'),
                                                      (2, 'digest-state-final-1', False, 'main'),
                                                      (3, 'digest-state-final-2', False, 'feature'),
                                                      (4, 'digest-state-final-3', True, 'main')]]
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run') as run:
            run.side_effect = [Mock(stdout=json.dumps([{'artifacts': artifacts}]).encode()),
                               Mock(stdout=json.dumps(self.trusted_run()).encode()), Mock(stdout=payload.getvalue())]
            root = Path(tmp) / 'state'
            restore_state.restore(root, 'owner/repo', 'main')
            self.assertIn('/2/zip', run.call_args.args[0][-1])
            self.assertTrue((root / 'prepared.json').exists())
            self.assertFalse((Path(tmp) / 'escape.json').exists())

    def test_api_failure_propagates_without_resetting_history(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore_state.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')):
            with self.assertRaises(subprocess.CalledProcessError):
                restore_state.restore(tmp, 'owner/repo', 'main')


class EvidenceRegressionTests(unittest.TestCase):
    def test_cloudflare_script_and_subscription_footer_keep_article_evidence(self):
        page = '<html><head><title>AI release</title><script src="cloudflare.js"></script></head><body><h1>AI release</h1><article>' + 'Public release details. ' * 40 + '</article><footer>Subscribe to continue receiving our newsletter.</footer></body></html>'
        response = Mock(status_code=200, text=page, url='https://example.com/release', headers={'Content-Type': 'text/html'})
        with patch.object(digest.requests, 'get', return_value=response):
            text, _ = digest.fetch_article(response.url, digest.load_config()['settings'])
        self.assertIn('Public release details.', text)

    def test_partial_rewrite_cannot_set_whole_edition_subject(self):
        original = {'tldr': 'Original brief', 'sections': [{'stories': [{'headline': 'One'}, {'headline': 'Two'}]}]}
        result = digest.apply_rewrites(original, {'subject': 'Only the first topic', 'tldr': 'New brief',
                                                 'stories': {1: {'headline': 'Updated first', 'summary': 'Facts'}}})
        self.assertNotIn('subject', result)
        self.assertEqual(result['tldr'], 'Original brief')

    def test_subject_control_characters_use_safe_fallback(self):
        content = json.dumps({'subject': 'News\r\nBcc: other@example.com', 'stories': [{'n': 1, 'headline': 'News', 'summary': 'Facts'}]})
        self.assertIsNone(digest.parse_summaries(content, 1)['subject'])

    def test_grouped_alternate_link_and_original_title_match_sent_history(self):
        item = dict(title='Original headline', link='https://first.test', source='First', summary='', snippet_chars=300, image='')
        other = {**item, 'link': 'https://second.test', 'source': 'Second'}
        grouped, _ = digest.dedupe([item, other])
        history = [{'urls': ['https://second.test'], 'titles': []}]
        self.assertTrue(digest.story_matches_history(grouped[0], history))

    def test_active_run_is_not_actionable_monitor_alert(self):
        now = datetime(2026, 11, 12, 16, 5, tzinfo=timezone.utc)
        runs = [{'id': 1, 'event': 'schedule', 'started': '2026-11-12T15:59:00Z', 'status': 'in_progress', 'markers': set()}]
        result = send_window.evaluate_monitor(now, runs, [])
        self.assertEqual(result['alerts'], [])


class CorruptStatePreviewTests(unittest.TestCase):
    def test_dry_run_ignores_corrupt_prepared_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = root / 'prepared.json'
            prepared.write_text('{bad json')
            item = dict(title='News', source='Example', link='https://example.com', summary='', snippet_chars=300, image='')
            config = digest.load_config()
            config['settings']['prepared_edition_path'] = str(prepared)
            output = root / 'preview.html'
            with patch('sys.argv', ['digest.py', '--dry-run', '--output', str(output)]), patch.object(digest, 'load_dotenv'), patch.object(digest, 'load_config', return_value=config), patch.object(digest, 'fetch_all', return_value={'Feed': [item]}), patch.object(digest, 'summarize', return_value=digest.fallback_digest([item])), patch.object(digest, 'send_email') as send, patch('builtins.print'):
                digest.main()
                send.assert_not_called()
            self.assertIn('Good Morning', output.read_text())
            self.assertEqual(prepared.read_text(), '{bad json')


class PrivateErrorLoggingTests(unittest.TestCase):
    def test_provider_status_error_never_formats_body_or_message(self):
        class ProviderStatusError(Exception):
            status_code = 429
            body = {'error': 'private-fixture-body', 'quota': 'PerDay'}

            @property
            def message(self):
                raise AssertionError('private provider message was accessed')

            def __str__(self):
                raise AssertionError('private provider error was formatted')

        error = ProviderStatusError()
        with patch.object(digest.openai, 'APIStatusError', ProviderStatusError):
            self.assertEqual(digest.describe_error(error), 'HTTP 429 ProviderStatusError')
        self.assertEqual(error.body['quota'], 'PerDay')  # Retry decisions retain the original exception.

    def test_arbitrary_exception_text_is_never_formatted(self):
        self.assertEqual(digest.describe_error(ValueError('private-fixture-message')), 'ValueError')

    def test_feed_exception_log_does_not_expose_its_message(self):
        settings = digest.load_config()['settings']
        with patch.object(digest, 'fetch_feed', side_effect=RuntimeError('private-fixture-message')), self.assertLogs(digest.log, level='ERROR') as logs:
            self.assertEqual(digest.fetch_all({'settings': settings, 'feeds': [{'name':'Fixture'}]}), {})
        self.assertNotIn('private-fixture-message', '\n'.join(logs.output))
        self.assertIn('RuntimeError', '\n'.join(logs.output))
