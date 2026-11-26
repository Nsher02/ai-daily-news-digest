"""Exercise scanner failure/privacy boundaries without downloading or executing tools."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import scan_secrets


class SecretScanTests(unittest.TestCase):
    def test_unverified_archive_is_never_executed_or_written(self):
        response = subprocess.CompletedProcess([], 0, stdout=b'untrusted archive', stderr=b'')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(scan_secrets.platform, 'system', return_value='Linux'), \
                    patch.object(scan_secrets.platform, 'machine', return_value='x86_64'), \
                    patch.object(scan_secrets.subprocess, 'run', return_value=response):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    scan_secrets.install(directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_findings_never_forward_scanner_stdout_or_stderr(self):
        sensitive = b'private-request-content-that-must-not-be-logged'
        response = subprocess.CompletedProcess([], 1, stdout=sensitive, stderr=sensitive)
        output = io.StringIO()
        with patch.object(scan_secrets.subprocess, 'run', return_value=response), redirect_stdout(output):
            self.assertEqual(scan_secrets.scan(Path('.'), Path('/unused')), 1)
        self.assertNotIn(sensitive.decode(), output.getvalue())
        self.assertIn('blocked', output.getvalue())

    def test_operational_errors_fail_closed_without_exposing_diagnostics(self):
        response = subprocess.CompletedProcess([], 2, stdout=b'', stderr=b'private diagnostic')
        with patch.object(scan_secrets.subprocess, 'run', return_value=response):
            with self.assertRaisesRegex(ValueError, 'blocked') as error:
                scan_secrets.scan(Path('.'), Path('/unused'))
        self.assertNotIn('private diagnostic', str(error.exception))

    def test_staged_scan_checks_additions_and_allows_removing_old_sensitive_text(self):
        diff = subprocess.CompletedProcess([], 0, stdout=b'--- a/file\n+++ b/file\n-old-sensitive\n+new-content\n', stderr=b'')
        result = subprocess.CompletedProcess([], 0, stdout=b'', stderr=b'')
        with patch.object(scan_secrets.subprocess, 'run', side_effect=[diff, result]) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(scan_secrets.scan(Path('.'), Path('/unused'), staged=True), 0)
        self.assertEqual(run.call_args.kwargs['input'], b'new-content')
        self.assertIn('--redact=100', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
