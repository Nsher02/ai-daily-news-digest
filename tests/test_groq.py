"""Independent-provider fallback tests; no external requests."""
import os
import time
import unittest
from unittest.mock import Mock, patch
import digest


class GroqBackupTests(unittest.TestCase):
    def test_separate_clients_keys_and_compact_prompt(self):
        gemini, groq = Mock(), Mock()
        gemini.chat.completions.create.side_effect = TimeoutError('unavailable')
        groq.chat.completions.create.return_value = Mock(choices=[Mock(message=Mock(content='{"ok":true}'))])
        with patch.dict(os.environ, {'LLM_API_KEY': 'gemini-test', 'GROQ_API_KEY': 'groq-test', 'GROQ_MODEL': 'openai/gpt-oss-120b'}, clear=True), patch.object(digest, 'OpenAI', side_effect=[gemini, groq]) as factory:
            result = digest.run_llm_chain('long prompt', __import__('json').loads, digest.load_config()['settings'], time.monotonic()+600, 'test', groq_prompt='compact JSON prompt')
        self.assertTrue(result['ok'])
        self.assertEqual(gemini.chat.completions.create.call_count, 2)
        self.assertEqual(factory.call_args_list[1].kwargs['api_key'], 'groq-test')
        self.assertEqual(factory.call_args_list[1].kwargs['base_url'], digest.GROQ_BASE_URL)
        request = groq.chat.completions.create.call_args.kwargs
        self.assertEqual(request['messages'][0]['content'], 'compact JSON prompt')
        self.assertEqual(request['max_completion_tokens'], 3000)

    def test_groq_failure_returns_to_gemini_with_bounded_wait(self):
        gemini, groq = Mock(), Mock()
        response = Mock(choices=[Mock(message=Mock(content='ok'))])
        gemini.chat.completions.create.side_effect = [TimeoutError(), TimeoutError(), response]
        groq.chat.completions.create.side_effect = TimeoutError()
        with patch.dict(os.environ, {'LLM_API_KEY':'g', 'GROQ_API_KEY':'q'}, clear=True), patch.object(digest, 'OpenAI', side_effect=[gemini, groq]), patch.object(digest.time, 'sleep') as sleep:
            self.assertEqual(digest.run_llm_chain('prompt', str, digest.load_config()['settings'], time.monotonic()+600, 'test'), 'ok')
        self.assertEqual(groq.chat.completions.create.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [65, 2])

    def test_successful_gemini_never_constructs_groq_client(self):
        with patch.dict(os.environ, {'LLM_API_KEY':'g', 'GROQ_API_KEY':'q'}, clear=True), patch.object(digest, 'OpenAI') as factory:
            factory.return_value.chat.completions.create.return_value = Mock(choices=[Mock(message=Mock(content='ok'))])
            digest.run_llm_chain('prompt', str, digest.load_config()['settings'], time.monotonic()+600, 'test')
            factory.assert_called_once()


class VerificationTests(unittest.TestCase):
    def test_verification_never_sends_incomplete_result(self):
        import verify_groq
        with patch.dict(os.environ, {'GROQ_API_KEY':'offline'}), patch('sys.argv', ['verify_groq.py','--send-email']), patch.object(verify_groq.digest, 'summarize_worker', return_value={'quality':'raw_headlines'}), patch.object(digest, 'send_email') as send:
            with self.assertRaises(SystemExit):
                verify_groq.main()
            send.assert_not_called()

    def test_complete_test_email_is_labeled_and_sent_once(self):
        import verify_groq
        item = dict(title='Synthetic fixture', link='https://example.com/test', source='Fixture', summary='Fictional example.', image='', snippet_chars=300)
        result = digest.fallback_digest([dict(item, title='Test '+str(i), link=item['link']+str(i)) for i in range(3)])
        result['quality'] = 'full'
        with patch.dict(os.environ, {'GROQ_API_KEY':'offline'}), patch('sys.argv', ['verify_groq.py','--send-email']), patch.object(verify_groq.digest, 'summarize_worker', return_value=result), patch.object(digest, 'send_email') as send:
            verify_groq.main()
        send.assert_called_once()
        self.assertIn('fictional', send.call_args.args[0])
        self.assertIn('TEST EMAIL', send.call_args.args[1])
