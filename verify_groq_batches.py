"""Live verification of 15 full Groq summaries. Never sends email or changes delivery state."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import digest
from groq_summary import GroqBudget, summarize_batches


def fixtures():
    topics = ['model compression', 'chip design', 'privacy checks', 'speech recognition',
              'robot navigation', 'software testing', 'translation', 'energy measurement',
              'accessibility', 'data labeling', 'weather forecasting', 'image detection',
              'document search', 'database indexing', 'network monitoring']
    items, stories = [], []
    for i, topic in enumerate(topics):
        article = (f'This is a fictional fixture about {topic}, not real news. '
                   f'Example Lab {i+1} published a benchmark for {topic} with {20+i} tasks. '
                   f'The team evaluated {3+i} systems on those tasks and published the evaluation code. '
                   'The report describes the measurements recorded during each run, provides the task definitions, and explains how the test scores were calculated. '
                   'It includes a table of results for each evaluated system, with a separate row for each task, so readers can inspect the individual measurements. '
                   'The benchmark and its code are available together with the report, allowing readers to repeat the documented evaluation using the same procedure. '
                   'The authors did not claim that the tested systems were suitable for production deployment, and the report does not include customer adoption figures or revenue estimates. '
                   'These materials describe an evaluation exercise rather than a commercial product launch.')
        item = dict(title=f'Example Lab {i+1} evaluates {topic}', link=f'https://example.com/fixture-{i+1}', source=f'Fictional lab {i+1}', summary=article, snippet_chars=1500, image='')
        items.append(item)
        stories.append(dict(ids=[i], headline=item['title'], summary='Initial short fixture summary.', links=[{'source':item['source'],'url':item['link']}], url=item['link'], image='', article={'source':item['source'],'text':article}))
    return items, stories


def main():
    load_dotenv()
    if not os.environ.get('GROQ_API_KEY'):
        raise SystemExit('GROQ_API_KEY is required')
    settings = digest.load_config()['settings']
    client = OpenAI(api_key=os.environ['GROQ_API_KEY'], base_url=digest.GROQ_BASE_URL, max_retries=0)
    items, stories = fixtures()
    started = time.monotonic()
    raw = summarize_batches(client, os.environ.get('GROQ_MODEL') or digest.DEFAULT_GROQ_MODEL,
                            stories, items, settings, started+settings['llm_step_cap'], GroqBudget())
    summaries = digest.parse_summaries(raw, len(stories))
    if set(summaries['stories']) != set(range(1,16)):
        raise SystemExit('Verification failed: not all 15 stories were rewritten')
    result = digest.apply_rewrites({'sections':[{'name':'Synthetic verification','stories':stories}], 'tldr':'Fifteen fictional fixtures for verification.', 'note':'Fictional examples. No email was sent.'}, summaries)
    Path('groq-full-verification.html').write_text(digest.render_html(result, 'Groq full-edition verification', 'AI Daily News Digest', '15 fictional fixtures'))
    stats = {'stories':len(summaries['stories']), 'quality':result['quality'],
             'word_counts':[len(s['summary'].split()) for s in summaries['stories'].values()],
             'elapsed_seconds':round(time.monotonic()-started)}
    print(json.dumps(stats))
    Path('groq-full-verification.json').write_text(json.dumps(stats,indent=2))


if __name__ == '__main__':
    main()
