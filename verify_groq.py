"""Explicit live Groq failover check; sends one synthetic test digest only with --send-email."""
import argparse
import os
import time
from unittest.mock import Mock, patch

from dotenv import load_dotenv
import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send-email', action='store_true')
    args = parser.parse_args()
    load_dotenv()
    if not os.environ.get('GROQ_API_KEY'):
        raise SystemExit('Configure GROQ_API_KEY before running the live verification.')
    config = digest.load_config()
    settings = dict(config['settings'], min_stories=3, max_stories=3)
    items = [dict(title=title, link='https://example.com/test-' + str(n), source='Synthetic test fixture',
                  summary=text, snippet_chars=500, image='')
             for n, (title, text) in enumerate([
                 ('Example Lab releases a test model', 'Synthetic example: Example Lab released a model with a 1000-token context window.'),
                 ('Example City adopts a procurement rule', 'Synthetic example: Example City requires a human review of software purchases starting in January.'),
                 ('Example University publishes a benchmark', 'Synthetic example: Example University published a benchmark with 20 tasks and released its evaluation code.')])]
    real_client = digest.OpenAI
    def client(**kwargs):
        if kwargs['base_url'] == digest.LLM_BASE_URL:
            mocked = Mock()
            mocked.chat.completions.create.side_effect = TimeoutError('Deliberately unavailable Gemini for backup verification')
            return mocked
        return real_client(**kwargs)
    def enrich(story, items, settings, deadline):
        story.update(article=None, article_reason='synthetic_test', image='')
        return story
    # No Gemini call, real feed fetch, state restore, or daily receipt mutation.
    with patch.object(digest, 'OpenAI', side_effect=client), patch.object(digest, 'enrich_story', side_effect=enrich):
        result = digest.summarize_worker(items, settings, time.monotonic()+settings['llm_step_cap'], lambda _: None)
    if result.get('quality') != 'full' or digest.story_count(result) != 3:
        raise SystemExit('Groq did not produce a complete three-story digest; no email sent.')
    print('Verified live Groq selection and rewriting through forced Gemini failure.')
    if args.send_email:
        result['note'] = 'TEST EMAIL: All stories below are fictional fixtures used to verify the Groq backup. This is not today’s news.'
        subject = 'AI Daily News Digest — Groq backup test (fictional examples)'
        text = digest.render_text(result, subject)
        html = digest.render_html(result, subject, config['email']['subject_prefix'], 'Groq backup verification')
        digest.send_email(subject, text, html, config['email'])
        print('One test email accepted by SMTP. Inbox delivery is unconfirmed.')


if __name__ == '__main__':
    main()
