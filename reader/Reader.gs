/** Private, read-only reader. No mail, AI, Drive, or public publishing API. */
const READER_REPO = 'Nsher02/ai-daily-news-digest';
const READER_ZONE = 'America/Chicago';

function assertReaderOwner_() {
  const owner = (PropertiesService.getScriptProperties().getProperty('OWNER_EMAIL') || '').trim().toLowerCase();
  const active = (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  if (!owner || !active || owner !== active) throw new Error('Access denied. Sign in with the reader owner account.');
}

function doGet(e) {
  // Static, content-free route only. No identity, cache, GitHub, or mail access.
  if (e && e.parameter && e.parameter.view === 'safari-test') {
    return HtmlService.createHtmlOutputFromFile('SafariTest').setTitle('Digest Safari Access Test')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  try {
    assertReaderOwner_();
  } catch (_) {
    return HtmlService.createHtmlOutput('Access denied. Sign in with the reader owner account.');
  }
  try {
    return HtmlService.createHtmlOutputFromFile('Index').setTitle('AI Daily News Digest')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  } catch (_) {
    console.error('Reader template could not be loaded. Verify an HTML file named Index exists.');
    return HtmlService.createHtmlOutput('Reader page could not load. Check that the project contains an HTML file named Index, then save and update the deployment.');
  }
}

function readerRequest_(path) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Reader credential is not configured.');
  return UrlFetchApp.fetch('https://api.github.com/repos/' + READER_REPO + path, {
    headers: {Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'},
    muteHttpExceptions: true, followRedirects: false
  });
}

function readerJson_(path) {
  const response = readerRequest_(path);
  if (response.getResponseCode() !== 200) throw new Error('GitHub is temporarily unavailable or the reader token needs attention.');
  return JSON.parse(response.getContentText());
}

function listReaderEditions_() {
  const groups = {};
  for (let page = 1; page <= 3; page++) {
    const data = readerJson_('/actions/artifacts?per_page=100&page=' + page);
    if (!Array.isArray(data.artifacts)) throw new Error('Unexpected edition list.');
    data.artifacts.forEach(a => {
      const match = /^digest-state-(prepared|final)-(\d+)-(\d+)$/.exec(a.name || '');
      if (!match || a.expired || !a.workflow_run || a.workflow_run.head_branch !== 'main' || String(a.workflow_run.id) !== match[2]) return;
      if (!Number.isSafeInteger(a.id) || !Number.isFinite(Date.parse(a.created_at))) return;
      const key = match[2];
      const candidate = Object.assign({}, a, {attempt: Number(match[3]), final: match[1] === 'final'});
      const old = groups[key];
      if (!old || candidate.attempt > old.attempt || (candidate.attempt === old.attempt && candidate.final && !old.final)) groups[key] = candidate;
    });
    if (data.artifacts.length < 100) break;
  }
  return Object.values(groups).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id-a.id).slice(0, 20);
}

function readReaderEdition_(artifact) {
  const run = readerJson_('/actions/runs/' + artifact.workflow_run.id);
  if (run.head_branch !== 'main' || run.path !== '.github/workflows/daily-digest.yml' || run.repository.full_name !== READER_REPO)
    throw new Error('Edition did not originate in the daily digest workflow.');
  const redirect = readerRequest_('/actions/artifacts/' + artifact.id + '/zip');
  if (redirect.getResponseCode() !== 302) throw new Error('Saved edition is unavailable.');
  const headers = redirect.getAllHeaders();
  const key = Object.keys(headers).find(k => k.toLowerCase() === 'location');
  const location = key ? String(headers[key]) : '';
  const host = /^https:\/\/([a-z0-9.-]+)(?::443)?\//i.exec(location);
  if (!host || !['.blob.core.windows.net', '.actions.githubusercontent.com'].some(suffix => host[1].toLowerCase().endsWith(suffix)))
    throw new Error('Unexpected download destination.');
  // Never forward the GitHub credential to the signed storage URL.
  const response = UrlFetchApp.fetch(location, {muteHttpExceptions: true, followRedirects: false});
  if (response.getResponseCode() !== 200) throw new Error('Edition download failed.');
  const blob = response.getBlob();
  if (blob.getBytes().length > 8000000) throw new Error('Edition archive exceeds size limit.');
  const files = Utilities.unzip(blob.setContentType('application/zip'));
  const file = files.find(f => f.getName() === 'prepared.json');
  if (!file || file.getBytes().length > 2000000) throw new Error('Edition content is missing or too large.');
  const record = JSON.parse(file.getDataAsString('UTF-8'));
  if (!/^\d{4}-\d{2}-\d{2}$/.test(record.digest_date || '') || typeof record.text_body !== 'string' || record.text_body.length > 80000 || typeof record.subject !== 'string')
    throw new Error('Invalid edition content.');
  // Return a strict display-only projection: no recipient, raw HTML, API replies, or delivery state.
  return {id: String(artifact.id), date: record.digest_date, subject: record.subject.slice(0, 300),
          quality: ['full', 'partial_pass_2', 'pass_1', 'raw_headlines'].includes(record.quality) ? record.quality : 'unknown',
          text: record.text_body, preparedAt: record.prepared_at || artifact.created_at};
}

function getReaderData(editionId) {
  assertReaderOwner_(); // Must precede every cache and network access.
  const requested = editionId === undefined || editionId === null || editionId === '' ? null : String(editionId);
  if (requested && !/^\d{1,20}$/.test(requested)) throw new Error('Invalid edition selection.');
  const cache = CacheService.getUserCache();
  const cacheKey = requested ? 'reader-edition-' + requested : 'last-reader-edition';
  try {
    const editions = listReaderEditions_();
    const candidates = requested ? editions.filter(a => String(a.id) === requested) : editions.slice(0, 5);
    if (!candidates.length) throw new Error('No saved edition is available.');
    let edition = null;
    let fallback = false;
    for (let i = 0; i < candidates.length; i++) {
      try { edition = readReaderEdition_(candidates[i]); fallback = i > 0; break; }
      catch (_) { if (requested) throw new Error('The selected edition is unavailable.'); }
    }
    if (!edition) throw new Error('No readable edition is available.');
    const result = {edition: edition, editions: editions.map(a => ({id: String(a.id), label: Utilities.formatDate(new Date(a.created_at), READER_ZONE, 'MMM d, yyyy HH:mm')})),
      fallback: fallback, cached: false};
    const serialized = JSON.stringify(result);
    if (Utilities.newBlob(serialized).getBytes().length < 95000) {
      try { cache.put(cacheKey, serialized, 21600); } catch (_) { /* Cache is optional. */ }
    }
    return finishReaderData_(result);
  } catch (_) {
    let saved = null;
    try { saved = JSON.parse(cache.get(cacheKey) || 'null'); } catch (_) { /* Fail closed. */ }
    if (saved && saved.edition && (!requested || saved.edition.id === requested)) {
      saved.cached = true;
      return finishReaderData_(saved);
    }
    throw new Error('Your digest is temporarily unavailable. Check the reader setup or try again later.');
  }
}

function finishReaderData_(result) {
  result.today = Utilities.formatDate(new Date(), READER_ZONE, 'yyyy-MM-dd');
  result.stale = result.edition.date !== result.today;
  return result;
}

/** Safe editor check: authorizes read access, logs only metadata, and never sends mail. */
function inspectReader() {
  const data = getReaderData();
  console.log(JSON.stringify({date: data.edition.date, quality: data.edition.quality, stale: data.stale, cached: data.cached}));
  return {date: data.edition.date, quality: data.edition.quality};
}
