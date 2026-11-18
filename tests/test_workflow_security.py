"""Offline checks for credential exposure and workflow access regressions."""
import fnmatch
import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def workflows():
    # BaseLoader preserves the literal YAML key 'on' instead of YAML 1.1 booleans.
    return {p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
            for p in (ROOT / '.github/workflows').glob('*.yml')}


class WorkflowSecurityTests(unittest.TestCase):
    def test_all_checkouts_discard_credentials_and_actions_are_allowlisted_pins(self):
        policy = json.loads((ROOT / '.github/allowed-actions.json').read_text())
        for filename, workflow in workflows().items():
            for job in workflow['jobs'].values():
                for step in job['steps']:
                    action = step.get('uses')
                    if not action:
                        continue
                    with self.subTest(workflow=filename, action=action):
                        self.assertRegex(action, r'^[\w.-]+/[\w.-]+@[a-f0-9]{40}$')
                        self.assertTrue(any(fnmatch.fnmatchcase(action, p) for p in policy['patterns_allowed']))
                        if action.startswith('actions/checkout@'):
                            self.assertEqual(step.get('with', {}).get('persist-credentials'), 'false')

    def test_workflow_tokens_never_gain_write_permissions(self):
        for filename, workflow in workflows().items():
            for scope in [workflow, *workflow['jobs'].values()]:
                with self.subTest(workflow=filename):
                    permissions = scope.get('permissions', {})
                    self.assertIsInstance(permissions, dict)
                    self.assertTrue(all(p in ('read', 'none') for p in permissions.values()))
            self.assertIn('permissions', workflow)
            self.assertNotIn('pull_request_target', workflow.get('on', {}))

    def test_delivery_github_token_is_limited_to_guard_and_restore(self):
        workflow = workflows()['daily-digest.yml']
        self.assertNotIn('GH_TOKEN', workflow.get('env', {}))
        job = workflow['jobs']['digest']
        self.assertNotIn('GH_TOKEN', job.get('env', {}))
        exposed = {s['name'] for s in job['steps'] if 'GH_TOKEN' in s.get('env', {})}
        self.assertEqual(exposed, {'Check send window', 'Restore digest state'})
        steps = {s.get('name'): s for s in job['steps']}
        self.assertNotIn('SMTP_PASSWORD', steps['Prepare digest'].get('env', {}))
        self.assertIn('SMTP_PASSWORD', steps['Send prepared digest']['env'])
        self.assertNotIn('LLM_API_KEY', steps['Send prepared digest']['env'])
        self.assertNotIn('GROQ_API_KEY', steps['Send prepared digest']['env'])

    def test_push_and_pull_request_tests_never_receive_service_secrets(self):
        for filename, workflow in workflows().items():
            if not {'push', 'pull_request'}.intersection(workflow.get('on', {})):
                continue
            with self.subTest(workflow=filename):
                self.assertNotRegex(json.dumps(workflow), r'secrets\s*\.')


if __name__ == '__main__':
    unittest.main()
