/** Shared-project variant: replace Code.gs; do not paste alongside the standalone monitor.
 * Only entry-point names differ. The hourly trigger must target checkDigest_.
 * Underscore functions cannot be called through google.script.run. */
const DIGEST_REPOSITORY = 'Nsher02/ai-daily-news-digest';
const DIGEST_WORKFLOW = 'daily-digest.yml';
const DIGEST_TIMEZONE = 'America/Chicago';

function githubPages_(path, field, token) {
  const items = [];
  for (let page = 1; page <= 10; page++) {
    const response = UrlFetchApp.fetch(
      'https://api.github.com/repos/' + DIGEST_REPOSITORY + path + '&per_page=100&page=' + page,
      {
        headers: {
          Authorization: 'Bearer ' + token,
          Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28'
        },
        muteHttpExceptions: true,
        followRedirects: false
      }
    );
    const status = response.getResponseCode();
    if (status !== 200) {
      throw new Error('GitHub returned HTTP ' + status + '. Check GitHub availability and token permissions/expiration.');
    }
    const data = JSON.parse(response.getContentText());
    if (!Array.isArray(data[field])) {
      throw new Error('GitHub returned an unexpected response.');
    }
    items.push(...data[field]);
    if (data[field].length < 100) return items;
  }
  throw new Error('GitHub pagination limit reached. Delivery could not be verified.');
}

function inspectDigest_(now, token) {
  const today = Utilities.formatDate(now, DIGEST_TIMEZONE, 'yyyy-MM-dd');
  const since = new Date(now.getTime() - 48 * 60 * 60 * 1000).toISOString();
  const runs = githubPages_(
    '/actions/workflows/' + DIGEST_WORKFLOW + '/runs?branch=main&created=' + encodeURIComponent('>=' + since),
    'workflow_runs', token
  );
  for (const run of runs) {
    const started = new Date(run.run_started_at || run.created_at);
    if (isNaN(started.getTime())) throw new Error('A GitHub run has an invalid timestamp.');
    const localDay = Utilities.formatDate(started, DIGEST_TIMEZONE, 'yyyy-MM-dd');
    const localTime = Utilities.formatDate(started, DIGEST_TIMEZONE, 'HH:mm');
    // Match send_window.py: early manual tests do not satisfy the morning edition.
    if (run.event === 'workflow_dispatch' && localDay === today && localTime < '07:45') continue;
    const jobs = githubPages_('/actions/runs/' + run.id + '/jobs?filter=all', 'jobs', token);
    const accepted = jobs.some(job => (job.steps || []).some(step =>
      step.name === 'SMTP accepted: ' + today && step.conclusion === 'success'
    ));
    if (accepted) return { date: today, status: 'smtp_accepted', runUrl: run.html_url };
  }
  return { date: today, status: 'missing_digest' };
}

/** Read-only setup check. Logs a result without sending alerts or changing daily state. */
function inspectDigestSetup_() {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('Add GITHUB_TOKEN under Project Settings > Script properties.');
  const result = inspectDigest_(new Date(), token);
  console.log(JSON.stringify(result));
  return result;
}

/** Trigger entry point. At most one alert per Chicago date after the morning deadline. */
function checkDigest_() {
  const now = new Date();
  const today = Utilities.formatDate(now, DIGEST_TIMEZONE, 'yyyy-MM-dd');
  if (Utilities.formatDate(now, DIGEST_TIMEZONE, 'HH:mm') < '10:20') return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try {
    const properties = PropertiesService.getScriptProperties();
    if (properties.getProperty('LAST_CHECK_DATE') === today) return;
    const token = properties.getProperty('GITHUB_TOKEN');
    const email = properties.getProperty('ALERT_EMAIL');
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      throw new Error('Add a valid ALERT_EMAIL under Project Settings > Script properties.');
    }
    let result;
    try {
      if (!token) throw new Error('The GitHub token is missing.');
      result = inspectDigest_(now, token);
    } catch (error) {
      // Keep tokens and raw HTTP responses out of logs and alert bodies.
      result = { status: 'verification_failed' };
    }
    if (result.status !== 'smtp_accepted') {
      const message = result.status === 'missing_digest'
        ? 'No eligible SMTP-accepted receipt was found for today’s AI Daily News Digest.'
        : 'The monitor could not check GitHub. Review GitHub availability and the monitor’s token permissions and expiration.';
      MailApp.sendEmail({
        to: email,
        subject: 'AI Daily News Digest monitor — ' + today,
        body: message + '\n\nDate is in America/Chicago.\nWorkflow: https://github.com/' +
          DIGEST_REPOSITORY + '/actions/workflows/' + DIGEST_WORKFLOW,
        name: 'AI Daily News Digest Monitor'
      });
    }
    // Commit only after checking succeeded or the alert was accepted by Google's mail service.
    properties.setProperty('LAST_CHECK_DATE', today);
    properties.setProperty('LAST_CHECK_STATUS', result.status);
  } finally {
    lock.releaseLock();
  }
}
