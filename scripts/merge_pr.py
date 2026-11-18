"""Merge an authorized PR only after its current commit passes the actual test job."""
import argparse
import json
import subprocess

REPO = 'Nsher02/ai-daily-news-digest'
BASE = f'repos/{REPO}'


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def check_pr(number, read=api):
    pr = read(f'{BASE}/pulls/{number}')
    if pr['state'] != 'open' or pr.get('draft'):
        raise ValueError('PR must be open and ready for review.')
    if (pr['base']['ref'] != 'main' or pr['base']['repo']['full_name'] != REPO
            or not pr['head'].get('repo') or pr['head']['repo']['full_name'] != REPO):
        raise ValueError('Expected a same-repository PR targeting main.')
    sha = pr['head']['sha']
    base_sha = read(f'{BASE}/git/ref/heads/main')['object']['sha']
    comparison = read(f'{BASE}/compare/{base_sha}...{sha}')
    if comparison['behind_by'] != 0:
        raise ValueError('PR is behind main. Update its branch, push, and wait for new tests.')
    runs = read(f'{BASE}/actions/workflows/tests.yml/runs?event=pull_request&head_sha={sha}&per_page=100')['workflow_runs']
    matches = [r for r in runs if r['head_sha'] == sha and r['event'] == 'pull_request'
               and any(p['number'] == number for p in r.get('pull_requests', []))]
    if not matches:
        raise ValueError('No pull-request test run exists for this exact commit.')
    run = max(matches, key=lambda r: r['id'])
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ValueError('The latest PR test run has not passed. Wait for or fix the checks.')
    jobs = read(f"{BASE}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100")['jobs']
    if not any(j['name'] == 'Offline regression tests' and j['status'] == 'completed'
               and j['conclusion'] == 'success' for j in jobs):
        raise ValueError('Offline regression tests did not complete successfully; skipped is not sufficient.')
    # Re-read both refs after checking CI. gh additionally matches the head atomically at merge.
    latest = read(f'{BASE}/pulls/{number}')
    if latest['state'] != 'open' or latest.get('draft') or latest['head']['sha'] != sha:
        raise ValueError('PR changed while checks were inspected. Run the check again.')
    if read(f'{BASE}/git/ref/heads/main')['object']['sha'] != base_sha:
        raise ValueError('main changed while checks were inspected. Update and recheck the PR.')
    return sha, run['html_url']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('number', type=int)
    parser.add_argument('--check-only', action='store_true', help='Validate without merging')
    args = parser.parse_args()
    try:
        sha, url = check_pr(args.number)
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Merge stopped: {error}') from error
    print(f'Current commit passed: {sha}\nTests: {url}', flush=True)
    if not args.check_only:
        subprocess.run(['gh', 'pr', 'merge', str(args.number), '--repo', REPO,
                        '--squash', '--match-head-commit', sha], check=True)


if __name__ == '__main__':
    main()
