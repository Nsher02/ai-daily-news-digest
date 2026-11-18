"""Fail-closed merge checks and the local direct-push boundary."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_push, merge_pr


class MergeChecksTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a'*40
        self.base = 'b'*40
        self.pr = {'state':'open','draft':False,'base':{'ref':'main','repo':{'full_name':merge_pr.REPO}},
                   'head':{'sha':self.sha,'repo':{'full_name':merge_pr.REPO}}}
        self.run = {'id':10,'head_sha':self.sha,'event':'pull_request','pull_requests':[{'number':3}],
                    'status':'completed','conclusion':'success','html_url':'https://example.com/check'}
        self.job = {'name':'Offline regression tests','status':'completed','conclusion':'success'}
        self.behind = 0
        self.pull_reads = self.base_reads = 0
        self.changed_head = self.changed_base = False

    def read(self, path):
        if '/pulls/' in path:
            self.pull_reads += 1
            value = copy.deepcopy(self.pr)
            if self.changed_head and self.pull_reads > 1:
                value['head']['sha'] = 'c'*40
            return value
        if '/git/ref/' in path:
            self.base_reads += 1
            sha = 'c'*40 if self.changed_base and self.base_reads>1 else self.base
            return {'object':{'sha':sha}}
        if '/compare/' in path:
            return {'behind_by':self.behind}
        if '/workflows/' in path:
            return {'workflow_runs':[copy.deepcopy(self.run)]}
        if '/jobs?' in path:
            return {'jobs':[copy.deepcopy(self.job)]}
        raise AssertionError(path)

    def test_current_tested_head_is_accepted(self):
        self.assertEqual(merge_pr.check_pr(3,self.read),(self.sha,self.run['html_url']))

    def test_failed_pending_skipped_and_missing_runs_are_rejected(self):
        for state in ('failure','cancelled','skipped',None):
            with self.subTest(state=state):
                self.run['conclusion'] = state
                with self.assertRaises(ValueError):
                    merge_pr.check_pr(3,self.read)
        self.run['conclusion'] = 'success'
        self.run['head_sha'] = 'c'*40
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_a_green_push_run_does_not_replace_the_pr_check(self):
        self.run['event'] = 'push'
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_a_different_pr_cannot_supply_checks(self):
        self.run['pull_requests'] = [{'number':4}]
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_skipped_job_is_not_a_successful_test(self):
        self.job['conclusion'] = 'skipped'
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_behind_main_is_rejected(self):
        self.behind = 1
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_refs_changing_during_check_are_rejected(self):
        for flag in ('changed_head','changed_base'):
            with self.subTest(flag=flag):
                self.setUp()
                setattr(self,flag,True)
                with self.assertRaises(ValueError):
                    merge_pr.check_pr(3,self.read)

    def test_drafts_and_other_repositories_are_rejected(self):
        self.pr['draft'] = True
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)
        self.pr['draft'] = False
        self.pr['head']['repo']['full_name'] = 'other/repo'
        with self.assertRaises(ValueError):
            merge_pr.check_pr(3,self.read)

    def test_cli_merge_matches_the_verified_sha(self):
        with patch('sys.argv',['merge_pr.py','3']), patch.object(merge_pr,'check_pr',return_value=(self.sha,'https://example.com')), patch.object(merge_pr.subprocess,'run') as run:
            merge_pr.main()
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--match-head-commit')+1],self.sha)
        self.assertNotIn('--admin',args)


class PushGuardTests(unittest.TestCase):
    def test_guard_blocks_main_creation_update_and_deletion(self):
        for local in ('refs/heads/main','refs/heads/codex/change','(delete)'):
            with self.subTest(local=local), patch('sys.stdin',io.StringIO(f'{local} abc refs/heads/main def\n')):
                self.assertEqual(check_push.main(),1)

    def test_feature_branch_is_allowed(self):
        with patch('sys.stdin',io.StringIO('refs/heads/codex/change abc refs/heads/codex/change def\n')):
            self.assertEqual(check_push.main(),0)

    def test_installed_hook_blocks_a_real_local_main_push(self):
        import shutil
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            repo, remote = folder/'repo', folder/'remote.git'
            def git(*args, cwd=None, check=True):
                return subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,check=check)
            git('init','--bare',str(remote))
            git('init','-b','main',str(repo))
            (repo/'scripts').mkdir()
            (repo/'.githooks').mkdir()
            shutil.copy(root/'scripts/check_push.py',repo/'scripts/check_push.py')
            shutil.copy(root/'.githooks/pre-push',repo/'.githooks/pre-push')
            (repo/'.githooks/pre-push').chmod(0o755)
            git('config','core.hooksPath','.githooks',cwd=repo)
            git('add','.',cwd=repo)
            git('-c','user.name=Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','-m','Test fixture',cwd=repo)
            rejected = git('push',str(remote),'main',cwd=repo,check=False)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('Direct pushes to main are blocked',rejected.stderr)
            git('switch','-c','codex/test',cwd=repo)
            git('push',str(remote),'codex/test',cwd=repo)
