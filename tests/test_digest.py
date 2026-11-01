import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import yaml

import digest
import send_window


class DeliveryTests(unittest.TestCase):
    def test_empty_feeds_are_not_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            with patch.dict('os.environ', {'GITHUB_OUTPUT': str(output)}), patch('sys.argv', ['digest.py']), patch.object(digest, 'load_dotenv'), patch.object(digest, 'fetch_all', return_value={}), patch.object(digest, 'send_email') as send:
                digest.main()
            self.assertIn('outcome=no_items', output.read_text())
            self.assertNotIn('outcome=sent', output.read_text())
            send.assert_not_called()

    def test_delivery_outcomes(self):
        item = dict(title='News', link='https://example.com/news', source='Source', summary='', snippet_chars=300, image='')
        for dry, fails, expected in [(False, False, 'sent'), (True, False, 'dry_run'), (False, True, 'failed')]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'output'
                with patch.dict('os.environ', {'GITHUB_OUTPUT': str(output)}), patch('sys.argv', ['digest.py'] + (['--dry-run'] if dry else [])), patch.object(digest, 'load_dotenv'), patch.object(digest, 'fetch_all', return_value={'Source': [item]}), patch.object(digest, 'summarize', return_value=digest.fallback_digest([item])), patch.object(digest, 'send_email', side_effect=RuntimeError('SMTP failed') if fails else None) as send, patch.object(Path, 'write_text'), patch('builtins.print'):
                    if fails:
                        with self.assertRaises(SystemExit):
                            digest.main()
                    else:
                        digest.main()
                outcomes = [line for line in output.read_text().splitlines() if line.startswith('outcome=')]
                self.assertEqual(outcomes[-1], 'outcome=' + expected)
                self.assertEqual(send.call_count, 0 if dry else 1)

def utc(stamp):
    return datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)


def run(event, started, marker_date=None, run_id=1):
    return {'id': run_id, 'event': event, 'started': started, 'markers': {f'SMTP accepted: {marker_date}'} if marker_date else set()}


class SendWindowTests(unittest.TestCase):
    def test_window_in_cst_and_cdt(self):
        # (UTC firing, expected send): CDT is UTC-5, CST is UTC-6.
        cases = [
            ('2026-10-15T12:53', True),   # CDT 7:53
            ('2026-10-15T11:53', False),  # CDT 6:53
            ('2026-10-15T12:23', False),  # CDT 7:23, before 7:45
            ('2026-10-15T14:53', True),   # CDT 9:53, late but inside window
            ('2026-10-15T15:00', False),  # CDT 10:00
            ('2026-12-15T13:53', True),   # CST 7:53
            ('2026-12-15T12:53', False),  # CST 6:53
            ('2026-12-15T14:23', True),   # CST 8:23
            ('2026-03-08T12:53', True),   # spring-forward day, CDT 7:53
            ('2026-03-08T13:53', True),   # spring-forward day, CDT 8:53
            ('2026-11-01T12:53', False),  # fall-back day, CST 6:53
            ('2026-11-01T13:53', True),   # fall-back day, CST 7:53
            ('2026-03-07T12:53', False),  # day before spring-forward, CST 6:53
        ]
        for stamp, expected in cases:
            with self.subTest(stamp=stamp):
                self.assertEqual(send_window.decide(utc(stamp), [])[0], expected)

    def test_every_morning_has_a_753_firing(self):
        workflow = yaml.load(Path('.github/workflows/daily-digest.yml').read_text(), Loader=yaml.BaseLoader)
        crons = [entry['cron'] for entry in workflow['on']['schedule']]
        self.assertIn('53 12,13,14 * * *', crons)
        self.assertNotIn('timezone', str(workflow['on']['schedule']))
        for day in ['2026-01-15', '2026-03-08', '2026-07-15', '2026-11-01']:
            local = [utc(f'{day}T{h}:53').astimezone(send_window.TZ).strftime('%H:%M') for h in (12, 13, 14)]
            self.assertIn('07:53', local)

    def test_second_run_skips_after_send(self):
        sent = run('schedule', '2026-12-15T13:53:10Z', '2026-12-15')
        self.assertEqual(send_window.decide(utc('2026-12-15T14:23'), [sent]), (False, "today's digest was already sent by run 1 (schedule)"))
        manual = run('workflow_dispatch', '2026-12-15T14:00:00Z', '2026-12-15')  # 8:00 CST
        self.assertFalse(send_window.decide(utc('2026-12-15T14:23'), [manual])[0])

    def test_unsent_or_old_runs_do_not_block(self):
        runs = [run('schedule', '2026-12-15T13:53:10Z'), run('workflow_dispatch', '2026-12-14T20:00:00Z', '2026-12-14')]
        self.assertTrue(send_window.decide(utc('2026-12-15T14:23'), runs)[0])

    def test_early_manual_run_does_not_block(self):
        early = run('workflow_dispatch', '2026-12-15T12:30:00Z', '2026-12-15')  # 6:30 CST
        self.assertTrue(send_window.decide(utc('2026-12-15T13:53'), [early])[0])
        early_cdt = run('workflow_dispatch', '2026-10-15T12:44:00Z', '2026-10-15')  # 7:44 CDT
        self.assertTrue(send_window.decide(utc('2026-10-15T12:53'), [early_cdt])[0])

    def test_reads_receipts_from_successful_steps(self):
        pages = {
            'runs': [{'workflow_runs': [
                {'id': 7, 'event': 'schedule', 'run_started_at': '2026-12-15T13:53:00Z', 'created_at': '2026-12-15T13:53:00Z'},
                {'id': 8, 'event': 'schedule', 'run_started_at': '2026-12-15T14:23:00Z', 'created_at': '2026-12-15T14:23:00Z'}]}],
            7: [{'jobs': [{'steps': [{'name': 'SMTP accepted: 2026-12-15', 'conclusion': 'success'}, {'name': 'Build and send digest', 'conclusion': 'success'}]}]}],
        }
        fake = lambda path: pages['runs'] if '/workflows/' in path else pages[int(path.split('/runs/')[1].split('/')[0])]
        with patch.object(send_window, 'gh_json', side_effect=fake):
            runs = send_window.recent_runs('owner/repo', utc('2026-12-15T14:23'), '8')
        self.assertEqual(runs, [{'id': 7, 'event': 'schedule', 'started': '2026-12-15T13:53:00Z', 'markers': {'SMTP accepted: 2026-12-15'}}])


def news(title, url, source='Publisher', summary=''):
    return dict(title=title, link=url, source=source, summary=summary, snippet_chars=300, image='')


class DuplicateTests(unittest.TestCase):
    def test_transitive_groups_preserve_evidence(self):
        items = [news('First', 'https://a.test/a', 'A'), news('Other', 'https://b.test/b', 'B'), news('First', 'https://b.test/b', 'B')]
        grouped, dropped = digest.dedupe(items)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]['evidence'], items)
        self.assertEqual(len(dropped), 2)
        self.assertEqual(len(digest.evidence_links(grouped, [0])), 2)
        self.assertNotIn('evidence', items[0])

    def test_same_publisher_does_not_gain_votes(self):
        items = [news('Same', 'https://a.test/a', 'The Verge'), news('Same', 'https://news.google.com/a', 'The Verge', 'Useful evidence'), news('Same', 'https://b.test/b', 'Other')]
        grouped, _ = digest.dedupe(items)
        prompt = digest.build_prompt(grouped, {'min_stories': 10, 'max_stories': 15})
        self.assertIn('2 distinct publishers', prompt)
        self.assertIn('Useful evidence', prompt)
        self.assertEqual(prompt.count('(The Verge)'), 1)
        self.assertEqual(len(digest.fallback_digest(grouped)['sections'][0]['stories'][0]['links']), 3)

    def test_distinct_items_and_empty_keys(self):
        items = [news('', ''), news('', ''), news('A', 'https://a.test/?id=1'), news('B', 'https://a.test/?id=2')]
        self.assertEqual(len(digest.dedupe(items)[0]), 4)


ISSUE = '''<h3>Navigation</h3><a href="/subscribe">Subscribe</a>
<article><a href="https://a.test/story?x=1&amp;y=2"><h3>First <b>story</b> (3 minute read)</h3></a><div>First summary <a href="https://wrong.test">context</a>.</div></article>
<article><h3><a href="/second">Second story</a></h3><div>Second summary</div></article>
<article><a href="https://ad.test"><h3>Great tool (Sponsor)</h3></a><div>Ad</div></article>
<article><h3>No link</h3></article>
<article><a href="javascript:alert(1)"><h3>Bad link</h3></a></article>'''


class IssueTests(unittest.TestCase):
    def test_article_links_and_sponsor_filter(self):
        stories = digest.parse_issue_stories(ISSUE, 'https://tldr.tech/ai/2026-10-30')
        self.assertEqual(len(stories), 2)
        self.assertEqual(stories[0]['title'], 'First story')
        self.assertEqual(stories[0]['link'], 'https://a.test/story?x=1&y=2')
        self.assertIn('First summary', stories[0]['summary'])
        self.assertEqual(stories[1]['link'], 'https://tldr.tech/second')
        self.assertFalse(digest.is_tldr_issue(stories[1]['link']))

    def test_feed_expansion_cap_timestamp_and_fallback(self):
        from datetime import datetime, timezone
        from unittest.mock import Mock
        entry = {'title': 'Issue', 'link': 'https://tldr.tech/ai/2026-10-30', 'summary': 'Existing snippet', 'published_parsed': (2026, 10, 30, 0, 0, 0, 4, 303, 0)}
        parsed = Mock(bozo=False, entries=[entry])
        feed = {'name': 'TLDR AI', 'expand_issue': True, 'url': 'https://tldr.tech/rss', 'max_items': 1}
        settings = {'request_timeout': 1, 'user_agent': 'test'}
        cutoff = datetime(2026, 10, 29, tzinfo=timezone.utc)
        with patch.object(digest.requests, 'get'), patch.object(digest.feedparser, 'parse', return_value=parsed), patch.object(digest, 'fetch_issue_stories', return_value=digest.parse_issue_stories(ISSUE, entry['link'])):
            items = digest.fetch_feed(feed, settings, cutoff)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'First story')
        self.assertEqual(items[0]['published'], datetime(2026, 10, 30, tzinfo=timezone.utc))
        for result in [[], RuntimeError('unavailable')]:
            with patch.object(digest.requests, 'get'), patch.object(digest.feedparser, 'parse', return_value=parsed), patch.object(digest, 'fetch_issue_stories', **({'side_effect': result} if isinstance(result, Exception) else {'return_value': result})):
                self.assertEqual(digest.fetch_feed(feed, settings, cutoff)[0]['title'], 'Issue')


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.items = [news(f'News {i}', f'https://example.com/{i}') for i in range(20)]

    def story(self, ids, headline=None):
        return {'ids': ids, 'headline': headline or f'Headline {ids}', 'summary': 'Factual summary'}

    def parse(self, sections, **extra):
        import json
        return digest.parse_digest(json.dumps({'sections': sections, **extra}), self.items, {'max_stories': 15})

    def test_cap_order_and_repeated_ids(self):
        data = self.parse([
            {'name': 'Research & tools', 'stories': [self.story([i]) for i in range(20)]},
            {'name': 'Top stories', 'stories': [self.story([0])]},
            {'name': 'Invented', 'stories': [self.story([19])]},
        ])
        stories = [s for section in data['sections'] for s in section['stories']]
        self.assertEqual(len(stories), 15)
        self.assertEqual(data['sections'][0]['name'], 'Top stories')
        self.assertEqual(len({i for s in stories for i in s['ids']}), 15)

    def test_invalid_entries_and_duplicate_headlines(self):
        data = self.parse([{'name': 'Top stories', 'stories': [None, self.story([True, False, -1, 100, '1']), self.story([0], ' '), self.story([0, 0, True], 'Valid'), self.story([1], 'Valid!'), {'ids': [2], 'headline': 'No summary', 'summary': []}]}])
        self.assertEqual(digest.story_count(data), 1)
        self.assertEqual(data['sections'][0]['stories'][0]['ids'], [0])
        self.assertEqual(data['sections'][0]['stories'][0]['url'], self.items[0]['link'])

    def test_short_selection_accounts_for_merges_and_exclusions(self):
        sections = [{'name': 'Top stories', 'stories': [self.story([0, 1, 2])]}]
        self.assertTrue(self.parse(sections, excluded_ids=list(range(3, 20)))['selection_complete'])
        self.assertFalse(self.parse(sections)['selection_complete'])
        self.assertFalse(self.parse(sections, excluded_ids=list(range(20)))['selection_complete'])
        self.assertFalse(self.parse(sections, excluded_ids=[True])['selection_complete'])

    def test_bad_roots_and_empty_selection(self):
        for content in ['null', '[]', '{}', '{"sections": null}', '{"sections": []}']:
            with self.subTest(content=content), self.assertRaises(ValueError):
                digest.parse_digest(content, self.items)

    def test_complete_short_digest_avoids_retry(self):
        import time
        from unittest.mock import Mock
        settings = digest.load_config()['settings']
        response = Mock()
        response.choices = [Mock(message=Mock(content='unused'))]
        for complete, expected_calls in [(True, 1), (False, 5)]:
            result = {'selection_complete': complete}
            with patch.object(digest, 'OpenAI') as client, patch.dict('os.environ', {'LLM_API_KEY': 'offline-test'}), patch.object(digest.time, 'sleep'):
                request = client.return_value.chat.completions.create
                request.return_value = response
                returned = digest.run_llm_chain('prompt', lambda _: result, settings, time.monotonic() + 600, 'test', count=lambda _: 1, want=10, final_try=False, accept_short=lambda d: d['selection_complete'])
                self.assertIs(returned, result)
                self.assertEqual(request.call_count, expected_calls)


class IntegrationTests(unittest.TestCase):
    def test_grouped_evidence_survives_both_passes_and_rendering(self):
        import json
        from unittest.mock import Mock
        items, _ = digest.dedupe([news('Launch', 'https://a.test', 'A', 'First snippet'), news('Launch', 'https://b.test', 'B', 'Second snippet')])
        replies = [
            {'tldr': 'Daily brief', 'excluded_ids': [], 'sections': [{'name': 'Top stories', 'stories': [{'ids': [0], 'headline': 'Launch', 'summary': 'Short summary'}]}]},
            {'tldr': 'Grounded brief', 'stories': [{'n': 1, 'headline': 'Grounded headline', 'summary': 'Expanded summary'}]},
        ]
        with patch.object(digest, 'OpenAI') as client, patch.dict('os.environ', {'LLM_API_KEY': 'offline-test'}), patch.object(digest, 'fetch_article', return_value=('Article evidence. ' * 30, '')):
            request = client.return_value.chat.completions.create
            request.side_effect = [Mock(choices=[Mock(message=Mock(content=json.dumps(reply)))]) for reply in replies]
            result = digest.summarize_worker(items, digest.load_config()['settings'], __import__('time').monotonic() + 600, lambda _: None)
        self.assertEqual(request.call_count, 2)
        self.assertIn('Second snippet', request.call_args_list[1].kwargs['messages'][0]['content'])
        story = result['sections'][0]['stories'][0]
        self.assertEqual(len(story['links']), 2)
        self.assertEqual(story['summary'], 'Expanded summary')
        rendered = digest.render_html(result, 'Title', 'Heading', 'Date')
        self.assertIn('https://a.test', rendered)
        self.assertIn('https://b.test', rendered)
        self.assertIn('Expanded summary', rendered)

    def test_guard_filters_failed_markers_and_fails_on_api_errors(self):
        import json
        import subprocess
        now = utc('2026-10-31T13:23')  # 8:23 CDT
        runs = {'workflow_runs': [{'id': 5, 'event': 'schedule', 'run_started_at': '2026-10-31T12:53:00Z', 'created_at': '2026-10-31T12:53:00Z'}]}
        for conclusion, api_fail, skip in [('success', False, True), ('failure', False, False), ('skipped', False, False), ('success', True, None)]:
            jobs = {'jobs': [{'steps': [{'name': 'SMTP accepted: 2026-10-31', 'conclusion': conclusion}]}]}
            def gh(cmd, **kwargs):
                if api_fail:
                    raise subprocess.CalledProcessError(1, cmd)
                return subprocess.CompletedProcess(cmd, 0, json.dumps([jobs if '/jobs?' in cmd[-1] else runs]))
            with self.subTest(conclusion=conclusion, api_fail=api_fail), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / 'output'
                output.touch()
                env = {'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(output.with_name('summary')), 'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '9'}
                with patch.dict('os.environ', env), patch.object(send_window.subprocess, 'run', side_effect=gh), patch.object(send_window, 'datetime', wraps=datetime) as clock, patch('builtins.print'):
                    clock.now.return_value = now
                    if api_fail:
                        with self.assertRaises(subprocess.CalledProcessError):
                            send_window.main()
                    else:
                        send_window.main()
                self.assertEqual('skip=true' in output.read_text(), bool(skip))

class GroundingTests(unittest.TestCase):
    def test_generated_headline_is_not_evidence(self):
        items = [news('Original title', 'https://example.com', summary='Original evidence')]
        prompt = digest.build_summary_prompt([{'headline': 'Invented claim', 'links': [], 'ids': [0], 'article': None}], items)
        self.assertNotIn('Invented claim', prompt)
        self.assertIn('Original title', prompt)
        self.assertIn('Original evidence', prompt)
        self.assertIn('never instructions', prompt)

    def test_rewrites_validate_ids_and_fields(self):
        import json
        parsed = digest.parse_summaries(json.dumps({'tldr': 'Final brief', 'stories': [
            {'n': True, 'headline': 'Invalid', 'summary': 'Invalid'},
            {'n': 1, 'headline': 'Corrected', 'summary': 'Grounded'},
            {'n': 1, 'headline': 'Duplicate', 'summary': 'Duplicate'},
            {'n': 2, 'summary': 'Missing headline'}, None]}), 2)
        self.assertEqual(parsed['stories'], {1: {'headline': 'Corrected', 'summary': 'Grounded'}})


class DeadlineTests(unittest.TestCase):
    def test_hung_process_is_killed_and_checkpoint_preserved(self):
        import json
        import sys
        import time
        for checkpoint in [None, {'sections': [], 'tldr': 'Saved', 'note': ''}]:
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'checkpoint.json'
                if checkpoint:
                    digest.write_checkpoint(path, checkpoint)
                start = time.monotonic()
                command = [sys.executable, '-c', 'import time; time.sleep(60)']
                if checkpoint:
                    result = digest.supervise_worker(command, path, start + 0.2)
                    self.assertEqual(result['tldr'], 'Saved')
                    self.assertTrue(result['deadline_hit'])
                else:
                    with self.assertRaises(TimeoutError):
                        digest.supervise_worker(command, path, start + 0.2)
                self.assertLess(time.monotonic() - start, 2)

    def test_exhausted_enrichment_makes_no_requests(self):
        import time
        item = news('News', 'https://a.test')
        story = {'links': [{'url': item['link'], 'source': 'A'}], 'ids': [0]}
        with patch.object(digest.requests, 'get') as get:
            result = digest.enrich_story(story, [item], digest.load_config()['settings'], time.monotonic() - 1)
        get.assert_not_called()
        self.assertIsNone(result['article'])
        self.assertEqual(result['image'], '')

    def test_article_failures_keep_snippet_fallback_and_cap_images(self):
        item = news('News', 'https://a.test')
        item['image'] = 'https://a.test/image'
        story = {'links': [{'url': item['link'], 'source': 'A'}], 'ids': [0]}
        with patch.object(digest, 'fetch_article', side_effect=TimeoutError), patch.object(digest, 'image_ok', return_value=False):
            result = digest.enrich_story(story, [item], digest.load_config()['settings'])
        self.assertIsNone(result['article'])
        self.assertIn('ARTICLE TEXT: unavailable', digest.build_summary_prompt([result], [item]))


class ReplayAndMetricsTests(unittest.TestCase):
    def test_replay_cli_is_offline_and_never_marks_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'preview.html'
            with patch('sys.argv', ['digest.py', '--replay', 'tests/fixtures/replay.json', '--output', str(output)]), patch.object(digest, 'load_dotenv', side_effect=AssertionError('credentials loaded')), patch.object(digest, 'fetch_all', side_effect=AssertionError('network')), patch.object(digest, 'OpenAI', side_effect=AssertionError('LLM')), patch.object(digest, 'send_email', side_effect=AssertionError('email')), patch.object(digest, 'record_outcome', side_effect=AssertionError('delivery output')):
                digest.main()
            rendered = output.read_text()
            self.assertIn('Example Lab releases 8B model', rendered)
            self.assertIn('Its weights are available to download.', rendered)

    def test_snapshot_does_not_save_credentials_or_extra_config(self):
        import json
        from datetime import datetime, timezone
        config = digest.load_config()
        config['secret'] = 'secret-sentinel'
        config['settings']['secret'] = 'secret-sentinel'
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'LLM_API_KEY': 'secret-sentinel'}):
            path = Path(tmp) / 'snapshot.json'
            digest.save_replay(path, [], {'sections': []}, config, datetime.now(timezone.utc))
            self.assertNotIn('secret-sentinel', path.read_text())
            self.assertEqual(json.loads(path.read_text())['version'], 1)

    def test_summary_reports_empty_feeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / 'summary'
            with patch.dict('os.environ', {'GITHUB_STEP_SUMMARY': str(summary)}), patch('sys.argv', ['digest.py']), patch.object(digest, 'load_dotenv'), patch.object(digest, 'fetch_all', return_value={}):
                digest.main()
            text = summary.read_text()
            self.assertIn('Feeds succeeded: 0', text)
            self.assertIn('Send outcome: no_items', text)
            self.assertIn('LLM attempts: 0', text)

    def test_summary_survives_failed_send(self):
        item = news('News', 'https://example.com')
        result = digest.fallback_digest([item])
        result.update(quality='pass_1', metrics={'llm_attempts': 3})
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / 'summary'
            with patch.dict('os.environ', {'GITHUB_STEP_SUMMARY': str(summary)}), patch('sys.argv', ['digest.py']), patch.object(digest, 'load_dotenv'), patch.object(digest, 'fetch_all', return_value={'Feed': [item]}), patch.object(digest, 'summarize', return_value=result), patch.object(digest, 'send_email', side_effect=RuntimeError('SMTP unavailable')):
                with self.assertRaises(SystemExit):
                    digest.main()
            text = summary.read_text()
            self.assertIn('Send outcome: failed', text)
            self.assertIn('LLM attempts: 3', text)

    def test_worker_attempt_metrics_survive_no_digest(self):
        import sys
        import time
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checkpoint.json'
            digest.write_checkpoint(path.with_name('metrics.json'), {'llm_attempts': 4})
            with self.assertRaises(TimeoutError) as error:
                digest.supervise_worker([sys.executable, '-c', 'import time; time.sleep(60)'], path, time.monotonic() + .2)
            self.assertEqual(error.exception.metrics['llm_attempts'], 4)

    def test_partial_rewrite_preserves_unrewritten_fields_and_tldr(self):
        import copy
        import json
        result = json.loads(Path('tests/fixtures/replay.json').read_text())['digest']
        second = copy.deepcopy(result['sections'][0]['stories'][0])
        second['headline'] = 'Second headline'
        result['sections'][0]['stories'].append(second)
        rewritten = digest.apply_rewrites(result, {'tldr': 'Should not apply', 'stories': {1: {'headline': 'New headline', 'summary': 'New summary'}}})
        self.assertEqual(rewritten['tldr'], 'Initial brief')
        self.assertEqual(rewritten['sections'][0]['stories'][1]['headline'], 'Second headline')
        self.assertEqual(rewritten['quality'], 'partial_pass_2')


class WorkerProcessTests(unittest.TestCase):
    def test_hung_article_thread_preserves_real_pass1_checkpoint(self):
        import os
        import sys
        import time
        script = '''
import json, os, sys, time
from pathlib import Path
from unittest.mock import patch
import digest
root = Path(sys.argv[1])
(root / 'pid').write_text(str(os.getpid()))
snapshot = json.loads(Path('tests/fixtures/replay.json').read_text())
items = snapshot['items']
settings = digest.load_config()['settings']
selection = digest.parse_digest(snapshot['digest']['replay_responses']['pass1'], items, settings)
with patch.object(digest, 'run_llm_chain', return_value=selection), patch.object(digest, 'fetch_article', side_effect=lambda *args: time.sleep(60)):
    digest.summarize_worker(items, settings, time.monotonic() + 60,
        lambda value: digest.write_checkpoint(root / 'checkpoint.json', value))
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            started = time.monotonic()
            result = digest.supervise_worker([sys.executable, '-c', script, tmp], root / 'checkpoint.json', started + 2)
            self.assertEqual(result['quality'], 'pass_1')
            self.assertEqual(digest.story_count(result), 1)
            self.assertTrue(result['deadline_hit'])
            self.assertLess(time.monotonic() - started, 4)
            pid = int((root / 'pid').read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
