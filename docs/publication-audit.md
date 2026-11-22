# Public-release audit — November 21, 2026

**Current release gate: keep the repository private until encrypted migration/cleanup and the remaining identity/image decisions are verified.** The subsequent encryption implementation and live verification are recorded in [encrypted-state.md](encrypted-state.md). The findings and counts below describe the original pre-encryption audit snapshot.

**Original audit decision: keep the active automation repository private for now.** No visibility setting, secret, remote log, artifact, schedule, or live Google project was changed. A clean public portfolio copy is the least disruptive way to show recruiters the project while retaining private delivery state.

## Scope and measured coverage

The pre-fix source baseline was `38d2804`. The audit fetched all available origin branches, tags, pull-request heads, and open pull-request merge refs; the checkout is not shallow. It inspected 57 reachable commits, 209 unique file blobs, and commit metadata across 35 local/fetched refs (including two synthetic PR merges). Local-only checkpoint refs were included. This does not recover deleted remote records or unadvertised/unreachable server objects.

The retained GitHub record inventory at the start of this audit contained:

- 105 workflow runs and all 107 available attempt-log ZIPs, containing 214 log members. Every requested archive downloaded successfully.
- 18 artifact ZIPs, containing 46 members. Every retained archive downloaded and was inspected; all 18 contain a prepared email record.
- Seven pull-request/issue records. No issue comments, review comments, releases, or deployments were returned. No Pages site or wiki was enabled.
- Eight repository secret **names** and zero repository variables. GitHub does not return saved secret values; none was requested, printed, or tested.

All 43 existing prompt files were included in the current-file and historical-text checks, including the old reader prompts. They contain historical instructions, configuration examples and a personal display name, not credential values detected by these checks. They remain unchanged and are historical documentation, not authorization to send mail or reinstate retired features.

Both original design images were visually inspected and retained. Basic TIFF/PNG metadata checks did not find GPS, camera-serial, artist, timestamp or raw-email fields in the inspected metadata; this is not a steganographic or redistribution-rights assessment. The images contain third-party Apple News design/content, so permission to redistribute them is an owner decision before public release.

Secret-format checks covered Google, Groq, OpenAI, GitHub, AWS, private-key headers, JWTs, credential-bearing URLs, quoted credential assignments, app-password-like strings, and signed/token URL candidates. No matching credential candidate was found in the reviewed history or retained logs/artifacts. This is a pattern-based result, **not a guarantee that every possible secret is absent**. Two locally configured credential values were also compared exactly against historical blobs and retained log/artifact members, with no matches. Other saved GitHub secret values were unavailable for exact comparison. Unknown formats, encoding, previously deleted records, and live validity are outside this conclusion. Discovered values were never used to authenticate.

Downloaded raw records and private review material were kept outside the repository. No sender/recipient values or personal author-email values are reproduced in this report. Counts describe the initial snapshot; new runs and expiration change the inventory.

## Finding 1: recovery state needed an origin check — fixed

Previously, `restore_state.py` selected the newest unexpired `digest-state-*` artifact with a matching branch label. It did not check the authoritative producing run. In a public repository, an executed fork PR workflow can supply an artifact with that name and a branch named `main`; a prefix and branch label do not establish trust. If prepared recipient/date checks also match, forged message/state content could reach the authenticated sending stage. Fork workflow approval and execution are prerequisites; no evidence of such a compromise was found in this private repository.

The fix checks the producing run's exact workflow path, event (`schedule` or `workflow_dispatch`), branch, repository, and head repository **before downloading** its contents. Untrusted records are skipped in favor of the newest trusted delivery state; an API verification failure still stops recovery instead of silently resetting state. Failed legitimate delivery runs remain eligible so recovery and duplicate prevention continue working. Existing state file basenames and archive paths are unchanged.

Synthetic offline tests reproduce the old acceptance path, reject PR/other-workflow/fork/other-repository/missing-identity cases, preserve existing state on API failure, and retain normal and failed-run recovery. Origin fields on all 18 actual retained artifact records also satisfy the new checks. No delivery workflow was dispatched for this validation.

## Finding 2: plaintext operational artifacts remain a publication blocker

Prepared and final uploads contain `prepared.json`, including sender and recipient addresses, prepared text/HTML, delivery metadata and story history. All 18 retained archives contain this private delivery information. They do **not** contain API keys or the SMTP app password detected by the checks above.

[GitHub readers can download workflow artifacts](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts). Making this repository public would broaden access to those records. Their seven-day expiration does not solve the ongoing issue: each daily run creates new plaintext artifacts. GitHub secret masking applies to logs, not arbitrary artifact file contents.

No existing artifact or run was deleted, and the recovery format was not redesigned during this audit. These records support duplicate prevention, prepared-message retry, and cross-day deduplication. Deleting run history also removes the SMTP-acceptance receipts used by the send-window check and Google monitor. Blind cleanup could affect live delivery.

Before publishing this exact repository, choose and implement private/authenticated recovery storage or authenticated encryption with a dedicated managed key, test restore/key-rotation/failure behavior, then plan the removal or expiration of **all** old plaintext artifacts. A clear-text SHA hash of an address is not a substitute for protecting private message content. Keep receipt/run evidence needed for current-day delivery guards. New storage/encryption configuration requires a concrete implementation and credential/maintenance decision; this audit does not silently introduce one.

Alternatively, create a clean public portfolio repository without operating secrets, personal operational history, or enabled delivery workflows; keep this working repository private. Do not simply fork it with all its history and expect the old material to disappear.

## Privacy decisions before any public release

- Commit author metadata contains the owner's academic email address. Deleting a current file does not remove commit metadata. Choose whether to publish that address; a noreply identity helps future commits but does not alter old ones. No history was rewritten or force-pushed.
- The display name used in email headers also appears in config and historical prompts. It was preserved to keep delivery unchanged and retain the requested prompt history. Decide whether it belongs in the public portfolio.
- Review redistribution rights for the original design references and third-party article content. Both images were preserved, as requested; this is not a legal clearance.
- Deleted reader code and old workflow/configuration versions are still present in Git history and fetched PR refs. The audited versions had no detected credential values, but publication would expose their historical implementation and instructions.

## Preventive hardening and existing controls

Provider failures now log only HTTP status and exception class, rather than raw provider error bodies/messages. Feed/issue failures use the same safe diagnostics. The original exception remains intact for retry/backoff decisions; email content, sender/recipient configuration, AI settings, delivery state, and schedules are unchanged. Tests cover private error-body/message suppression.

Current workflows have read-only token permissions, full allowlisted action pins, discarded checkout credentials and no `pull_request_target` trigger. Automatic push/PR tests receive no service secrets. AI preparation does not receive the SMTP password; the sending step does not receive AI keys. The default workflow token is read-only and cannot approve PRs. Implicit action/runtime credentials still exist; steps in a job are not separate security isolation boundaries.

The saved secret values, account-level apps/tokens and outside-collaborator workflow-approval policy could not be independently established through this repository audit. Before a public rollout, require approval for outside-collaborator workflows, retain least-privilege settings, and review every workflow/dependency change before merging. This is additional to fixing state provenance, not a replacement for it.

## Publication checklist

1. Keep visibility private until the operational artifact issue is resolved, or choose a sanitized public portfolio copy.
2. Decide whether the academic author address, display name and third-party references may be public. Do not rewrite history without a reviewed migration/backup plan, including branches, PR refs and existing clones.
3. Finish storage protection and safe historical-artifact cleanup if publishing the operating repository. Do not delete live receipts or recovery state ad hoc. Re-inventory artifacts/logs at the actual release time.
4. Enable/verify public-repository secret scanning and push protection where available, outside-contributor workflow approval, and supported branch protection before accepting external contributions.
5. Test signed-out public visibility only after a separate explicit release decision. Changing visibility was not part of this task.

Local validation passed 108 offline Python tests, seven mocked Google monitor scenarios, syntax/manifest checks and workflow lint. The fix PR must also pass the current commit’s Offline regression tests before merging. These do not establish live SMTP, provider availability, inbox delivery, or hosted Google settings. No test email, AI call, delivery dispatch, secret rotation, remote deletion, history rewrite, or visibility change was performed.
