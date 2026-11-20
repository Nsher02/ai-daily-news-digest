const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const shared = process.argv.includes('--shared');
const source = fs.readFileSync(shared ? 'reader/Monitor.gs' : 'monitoring/google_apps_script.gs', 'utf8');
const checkName = shared ? 'checkDigest_' : 'checkDigest';
const inspectName = shared ? 'inspectDigestSetup_' : 'inspectDigest';
function setup({receipt = true, hour = 16, status = 200, earlyManual = false, failMail = false} = {}) {
  const store = {GITHUB_TOKEN: 'offline-token', ALERT_EMAIL: 'reader@example.com'};
  const emails = [];
  let requests = 0;
  class Clock extends Date { constructor(...args) { super(...(args.length ? args : [`2026-11-12T${hour}:30:00Z`])); } }
  const context = vm.createContext({
    Date: Clock, console: {log() {}},
    Utilities: {formatDate(date, zone, pattern) {
      const parts = new Intl.DateTimeFormat('en-GB', {timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(date);
      const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
      return pattern === 'yyyy-MM-dd' ? `${p.year}-${p.month}-${p.day}` : `${p.hour}:${p.minute}`;
    }},
    PropertiesService: {getScriptProperties: () => ({getProperty: k => store[k], setProperty: (k,v) => {store[k] = v;}})},
    LockService: {getScriptLock: () => ({tryLock: () => true, releaseLock() {}})},
    MailApp: {sendEmail(message) {if (failMail) throw Error('Mail failed'); emails.push(message);}},
    UrlFetchApp: {fetch(url) {
      requests++;
      const data = url.includes('/jobs?')
        ? {jobs: [{steps: [{name: 'SMTP accepted: 2026-11-12', conclusion: receipt ? 'success' : 'skipped'}]}]}
        : {workflow_runs: [{id: 1, event: earlyManual ? 'workflow_dispatch' : 'schedule', run_started_at: earlyManual ? '2026-11-12T12:00:00Z' : '2026-11-12T13:50:00Z', html_url: 'https://github.com/example/run'}]};
      return {getResponseCode: () => status, getContentText: () => JSON.stringify(data)};
    }}
  });
  vm.runInContext(source, context);
  return {context, store, emails, requests: () => requests};
}
let s = setup();
s.context[checkName](); s.context[checkName]();
assert.equal(s.emails.length, 0); assert.equal(s.store.LAST_CHECK_STATUS, 'smtp_accepted'); assert.equal(s.requests(), 2);
s = setup({receipt: false}); s.context[checkName](); s.context[checkName](); assert.equal(s.emails.length, 1);
s = setup({status: 403}); s.context[checkName](); assert.equal(s.store.LAST_CHECK_STATUS, 'verification_failed'); assert.equal(s.emails.length, 1);
s = setup({hour: 14}); s.context[checkName](); assert.equal(s.requests(), 0); assert.equal(s.emails.length, 0);
s = setup({earlyManual: true}); s.context[checkName](); assert.equal(s.emails.length, 1);
s = setup({receipt: false}); s.context[inspectName](); assert.equal(s.emails.length, 0); assert.equal(s.store.LAST_CHECK_DATE, undefined);
s = setup({receipt: false, failMail: true}); assert.throws(() => s.context[checkName]()); assert.equal(s.store.LAST_CHECK_DATE, undefined);
console.log((shared ? 'Shared project: ' : 'Standalone: ') + '7 mocked monitor scenarios passed. No network calls or email sends.');
