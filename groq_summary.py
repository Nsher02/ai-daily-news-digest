"""Token-budgeted Groq calls and complete, resumable story rewriting."""
import json
import logging
import time

log = logging.getLogger(__name__)
OUTPUT_TOKENS = 2600
MINUTE_BUDGET = 7500  # Leave headroom below the published 8,000 TPM free limit.


class GroqBudget:
    def __init__(self):
        self.requests = []
        self.total = 0

    def count_tokens(self, prompt):
        import tiktoken
        # GPT-OSS uses the o200k vocabulary; leave room for provider chat framing.
        return len(tiktoken.get_encoding('o200k_base').encode(prompt, disallowed_special=())) + 256

    def fits(self, prompt):
        return self.count_tokens(prompt) + OUTPUT_TOKENS <= MINUTE_BUDGET

    def reserve(self, prompt, deadline):
        tokens = self.count_tokens(prompt) + OUTPUT_TOKENS
        if tokens > MINUTE_BUDGET:
            raise ValueError('Groq request exceeds the free-tier per-request token budget')
        if self.total + tokens > 100000:
            raise RuntimeError('Groq per-run safety budget exhausted')
        while True:
            now = time.monotonic()
            self.requests = [r for r in self.requests if now - r[0] < 65]
            if sum(r[1] for r in self.requests) + tokens <= MINUTE_BUDGET:
                break
            wait = max(0, self.requests[0][0] + 65 - now)
            if now + wait + 1 >= deadline:
                raise TimeoutError('No stage time remains for Groq rate-limit cooldown')
            log.info('Groq free-tier pacing: waiting %.1fs', wait)
            time.sleep(wait)
        if deadline - time.monotonic() < 1:
            raise TimeoutError('Groq stage deadline reached')
        reservation = [time.monotonic(), tokens]
        self.requests.append(reservation)
        self.total += tokens
        return reservation

    def complete(self, reservation, usage):
        actual = getattr(usage, 'total_tokens', None)
        if type(actual) is int and actual > 0:
            self.total += actual - reservation[1]
            reservation[1] = actual


def request_groq(client, model, prompt, settings, deadline, budget, on_attempt=None):
    reservation = budget.reserve(prompt, deadline)
    options = {'reasoning_effort': 'low'} if model.startswith('openai/gpt-oss-') else {}
    if on_attempt:
        on_attempt()
    response = client.chat.completions.create(
        model=model, messages=[{'role': 'user', 'content': prompt}],
        response_format={'type': 'json_object'}, temperature=0.2,
        max_completion_tokens=OUTPUT_TOKENS,
        timeout=min(settings['llm_timeout'], deadline-time.monotonic()),
        extra_body=options,
    )
    budget.complete(reservation, response.usage)
    if response.choices[0].finish_reason == 'length':
        raise ValueError('Groq output was truncated; refusing incomplete JSON')
    return response.choices[0].message.content


def summarize_batches(client, model, stories, items, settings, deadline, budget,
                      on_attempt=None, on_progress=None):
    # Import at call time to keep digest.py's shared parser and grounding contract.
    import digest
    completed = {}
    total = len(stories)
    subject, tldr = None, ''
    while len(completed) < total:
        pending = [n for n in range(1, total+1) if n not in completed]
        selected = []
        prompt = ''
        for n in pending[:3]:
            candidate = selected + [n]
            batch = [stories[i-1] for i in candidate]
            proposed = digest.build_summary_prompt(batch, items)
            if budget.fits(proposed):
                selected, prompt = candidate, proposed
            else:
                break
        if not selected:
            # An oversized source group must not prevent all other stories being processed.
            selected = [pending[0]]
            for cap in (3000, 1800, 900, 400):
                prompt = digest.build_summary_prompt([stories[selected[0]-1]], items, evidence_chars=cap)
                if budget.fits(prompt):
                    break
            if not budget.fits(prompt):
                raise ValueError('One story cannot fit the Groq token budget')
        batch = [stories[i-1] for i in selected]
        accepted = False
        # Retry only missing/short stories in the next batch, never overwrite completed ones.
        for attempt in range(2):
            try:
                raw = request_groq(client, model, prompt, settings, deadline, budget, on_attempt)
                parsed = digest.parse_story_summaries(raw, batch)
                added = {selected[local-1]: rewrite for local, rewrite in parsed['stories'].items()}
                if not added:
                    raise ValueError('Groq returned no sufficiently complete paragraphs')
                completed.update(added)
                # Batch-local TLDR/subject must not describe the entire edition.
                if total == len(batch) and len(completed) == total:
                    subject, tldr = parsed.get('subject'), parsed.get('tldr', '')
                payload = {'stories': [dict(n=n, **value) for n, value in sorted(completed.items())],
                           'subject': subject, 'tldr': tldr}
                if on_progress:
                    on_progress(json.dumps(payload))
                log.info('Groq full summaries: %d/%d stories', len(completed), total)
                accepted = True
                break
            except Exception as error:
                log.warning('Groq batch attempt %d failed (%s)', attempt+1, type(error).__name__)
                # Invalid credentials/model and oversize requests will not improve on retry.
                if getattr(error, 'status_code', None) in (400, 401, 403, 404, 413):
                    raise
                if attempt == 1:
                    raise
        if not accepted:
            break
    return json.dumps({'stories': [dict(n=n, **value) for n, value in sorted(completed.items())],
                       'subject': subject, 'tldr': tldr})
