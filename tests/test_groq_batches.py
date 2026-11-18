import json
import unittest
from unittest.mock import Mock, patch

import digest
import groq_summary as groq


PARAGRAPH = ('Example Lab released its benchmark after completing the published evaluation procedure. '
             'The benchmark contains twenty tasks and includes the evaluation code for each task, which the lab has made available with its report. '
             'The report describes the measurements collected during the evaluation and explains how the individual tasks were scored by the team. '
             'Those published materials allow readers to inspect the procedure and compare the reported results using the same evaluation tasks. '
             'The evaluation report also provides the task definitions and individual measurements, giving readers a documented basis for repeating each part of the procedure.')


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.items = [dict(title=f'Original {i}', link=f'https://example.com/{i}', source='Source', summary=PARAGRAPH, snippet_chars=300) for i in range(15)]
        self.stories = [dict(ids=[i], links=[{'source':'Source','url':item['link']}], article={'source':'Source','text':PARAGRAPH*8}) for i,item in enumerate(self.items)]
        self.clock = [0.0]
        self.patches = [patch.object(groq.time, 'monotonic', side_effect=lambda:self.clock[0]),
                        patch.object(groq.time, 'sleep', side_effect=lambda n:self.clock.__setitem__(0,self.clock[0]+n)),
                        patch.object(groq.GroqBudget, 'count_tokens', return_value=3000)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def run_batches(self, missing=False, bad_after=None):
        client = Mock()
        seen = []
        def request(**kwargs):
            prompt = kwargs['messages'][0]['content']
            seen.append(prompt)
            if bad_after and len(seen) > bad_after:
                raise TimeoutError('provider unavailable')
            size = prompt.count('=== Story ')
            size = 1 if missing else size
            stories = [dict(n=i,headline='Grounded headline',summary=PARAGRAPH) for i in range(1,size+1)]
            response = Mock(choices=[Mock(finish_reason='stop',message=Mock(content=json.dumps({'stories':stories,'subject':'Batch-only subject','tldr':'Batch-only brief'})))])
            response.usage.total_tokens = 4000
            return response
        client.chat.completions.create.side_effect = request
        checkpoints = []
        if bad_after:
            with self.assertRaises(TimeoutError):
                groq.summarize_batches(client,'openai/gpt-oss-120b',self.stories,self.items,{'llm_timeout':60},900,groq.GroqBudget(),on_progress=checkpoints.append)
            return checkpoints
        result = json.loads(groq.summarize_batches(client,'openai/gpt-oss-120b',self.stories,self.items,{'llm_timeout':60},1800,groq.GroqBudget(),on_progress=checkpoints.append))
        return result, seen, checkpoints

    def test_all_fifteen_full_paragraphs_in_five_batches(self):
        result, seen, checkpoints = self.run_batches()
        self.assertEqual([s['n'] for s in result['stories']],list(range(1,16)))
        self.assertEqual(len(seen),5)
        self.assertEqual(len(checkpoints),5)
        self.assertTrue(all(len(s['summary'].split())>=90 for s in result['stories']))
        self.assertTrue(all(PARAGRAPH*8 in p for p in seen))
        self.assertIsNone(result['subject'])
        self.assertEqual(result['tldr'],'')
        self.assertEqual(self.clock[0],260)

    def test_missing_stories_only_are_retried_with_correct_global_numbers(self):
        result, seen, _ = self.run_batches(missing=True)
        self.assertEqual(len(result['stories']),15)
        self.assertEqual(len(seen),15)
        self.assertNotIn('Original 0',seen[1])
        self.assertIn('Original 1',seen[1])

    def test_completed_batches_survive_later_failure(self):
        checkpoints = self.run_batches(bad_after=2)
        self.assertEqual(len(json.loads(checkpoints[-1])['stories']),6)

    def test_budget_wont_sleep_beyond_deadline(self):
        budget = groq.GroqBudget()
        budget.reserve('prompt', 100)
        with self.assertRaises(TimeoutError):
            budget.reserve('prompt', 30)
        self.assertEqual(self.clock[0],0)

    def test_oversize_request_is_not_sent(self):
        with patch.object(groq.GroqBudget,'count_tokens',return_value=8000):
            with self.assertRaises(ValueError):
                groq.GroqBudget().reserve('prompt',900)

    def test_truncated_output_is_not_accepted(self):
        client = Mock()
        client.chat.completions.create.return_value = Mock(usage=Mock(total_tokens=4000), choices=[Mock(finish_reason='length')])
        with self.assertRaisesRegex(ValueError, 'truncated'):
            groq.request_groq(client, 'openai/gpt-oss-120b', 'prompt', {'llm_timeout':60}, 900, groq.GroqBudget())

    def test_short_paragraphs_are_retried_and_never_checkpointed(self):
        client = Mock()
        raw = json.dumps({'stories':[{'n':1,'headline':'Headline','summary':'Too short.'}]})
        response = Mock(usage=Mock(total_tokens=4000), choices=[Mock(finish_reason='stop', message=Mock(content=raw))])
        client.chat.completions.create.return_value = response
        progress = Mock()
        with self.assertRaises(ValueError):
            groq.summarize_batches(client, 'openai/gpt-oss-120b', self.stories[:1], self.items, {'llm_timeout':60}, 900, groq.GroqBudget(), on_progress=progress)
        self.assertEqual(client.chat.completions.create.call_count,2)
        progress.assert_not_called()


class WorkerCheckpointTests(unittest.TestCase):
    def test_batch_progress_survives_worker_exception_and_is_replayable(self):
        import copy
        from verify_groq_batches import fixtures
        items, stories = fixtures()
        initial = {'sections':[{'name':'Top stories','stories':copy.deepcopy(stories)}], 'tldr':'Initial edition brief', 'note':''}
        def chain(prompt, parse, settings, deadline, label, **kwargs):
            if label == 'pass 1':
                return initial
            raw = json.dumps({'stories':[dict(n=n,headline='Full headline',summary=PARAGRAPH) for n in range(1,7)]})
            kwargs['on_response'](raw)
            raise TimeoutError('later batch failure')
        saved = []
        with patch.object(digest,'run_llm_chain',side_effect=chain), patch.object(digest,'enrich_story',side_effect=lambda story,*args:story):
            result = digest.summarize_worker(items,digest.load_config()['settings'],__import__('time').monotonic()+900,saved.append)
        self.assertEqual(result['quality'],'partial_pass_2')
        self.assertEqual(result['sections'][0]['stories'][5]['summary'],PARAGRAPH)
        self.assertEqual(result['sections'][0]['stories'][6]['summary'],'Initial short fixture summary.')
        replay = digest.parse_summaries(result['replay_responses']['pass2'],15)
        self.assertEqual(set(replay['stories']),set(range(1,7)))
        self.assertEqual(result['tldr'],'Initial edition brief')


class SharedEditorialRulesTests(unittest.TestCase):
    def test_rich_source_requires_same_full_paragraph_contract(self):
        from verify_groq_batches import fixtures
        _, stories = fixtures()
        short = json.dumps({'stories':[{'n':1,'headline':'Original headline','summary':'A brief rewrite.'}]})
        with self.assertRaises(ValueError):
            digest.parse_story_summaries(short, stories[:1])
        valid = json.dumps({'stories':[{'n':1,'headline':'Original headline','summary':PARAGRAPH}]})
        self.assertEqual(digest.parse_story_summaries(valid, stories[:1])['stories'][1]['summary'], PARAGRAPH)

    def test_sparse_source_does_not_force_padding(self):
        stories = [{'article':None}]
        raw = json.dumps({'stories':[{'n':1,'headline':'Original headline','summary':'A source-supported short summary.'}]})
        self.assertEqual(len(digest.parse_story_summaries(raw, stories)['stories']),1)

    def test_partial_result_cannot_replace_edition_subject_or_brief(self):
        raw = json.dumps({'subject':'Incomplete scope','tldr':'Only one story','stories':[{'n':1,'headline':'Headline','summary':'Supported summary.'}]})
        parsed = digest.parse_story_summaries(raw,[{'article':None},{'article':None}])
        self.assertIsNone(parsed['subject'])
        self.assertEqual(parsed['tldr'],'')
