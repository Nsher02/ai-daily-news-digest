# GitHub access audit — November 18, 2026

## Verified repository settings

- Repository `Nsher02/ai-daily-news-digest` is private; only `Nsher02` appeared in the collaborator list, with owner/admin access.
- No repository deploy keys or webhooks were returned. This does not establish which account-level OAuth apps, GitHub Apps, SSH keys, or personal tokens can access the account.
- Default workflow permissions are read-only; workflows cannot approve pull requests.
- GitHub Actions now allows only the four action repositories in [the allowlist](../.github/allowed-actions.json), with full commit-SHA pinning required at repository level. Other GitHub-owned and marketplace actions are not broadly allowed. Version wildcards permit reviewed pin updates, but the SHA requirement still rejects floating tags.
- Dependabot vulnerability alerts were enabled and verified. Weekly dependency and action update PRs are configured in `.github/dependabot.yml`; updates are not automatically merged.
- Every workflow checkout disables persisted credentials. Explicit `GH_TOKEN` exposure in the delivery job is limited to the send-window check and artifact restoration, where repository Actions read access is required. Package installation, AI preparation, and SMTP steps do not receive that environment variable. The GitHub platform still supplies implicit action/runtime credentials; this is not a separate security isolation boundary between steps in a job.
- AI keys and the SMTP password remain separated by preparation/sending step. Push/PR regression tests receive no service secrets.
- Original prompts and design images are retained. At the original audit, seven-day prepared artifacts contained plaintext recipient/message data. Current uploads use authenticated encryption; complete the [encrypted-state migration and legacy cleanup](encrypted-state.md) before publication. Actions read access alone cannot decrypt the new artifacts without the separate state key.

## What could not be established or changed

- The active GitHub CLI OAuth session reports `repo`, `workflow`, `read:org`, and `gist` scopes. It is an account-level developer credential, not the narrowly scoped scheduler or monitor credential. Its broader access was not revoked or changed because this could disrupt other authorized projects. Review its ongoing necessity under [authorized OAuth apps](https://github.com/settings/applications); do not copy it into external services.
- GitHub returned 403 when checking branch protection: this private repository requires GitHub Pro or another supported paid plan for that feature. The repository was not made public and no plan was changed. Tests on a push cannot prevent an owner from making a direct push; do not interpret the test workflow as enforced branch protection.
- GitHub returned 422 for disabling private forks: that setting can only be changed for organization-owned private repositories. With only the owner listed as collaborator, no other collaborator access was found, but account-level token/app access is a separate review.
- Account 2FA status was not returned by the current API response. Review [password and authentication settings](https://github.com/settings/security) if needed; this audit does not establish whether 2FA is enabled.
- Repository APIs do not expose the actual permissions or expiry of the personal tokens stored at cron-job.org or Google Apps Script. Those must be inspected in the account UI. Secret names and update dates were checked without reading or exposing secret values.

## External tokens confirmed by the owner

On November 18, 2026, the owner reported checking the actual service tokens in GitHub and confirming the one-repository selections and permissions above:

- cron-job.org scheduler: expires **November 1, 2027**; suggested renewal reminder **October 25, 2027**.
- Google digest monitor: expires **November 12, 2027**; suggested renewal reminder **November 5, 2027**.

These dates and permissions are owner-confirmed, not independently exposed by the repository API. No replacement or permission change is needed for these correctly scoped tokens. Their existing finite, roughly annual expiry was preserved; shortening to 90 days is optional and increases renewal work. No reminders were created automatically. The repository fork listing was also empty at audit time.

## Manual token review

1. Open [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens). Inspect the actual token used for each service, not just a token with a similar name. Never post token values or screenshots containing them.
2. The **cron-job.org scheduler** token should have resource owner `Nsher02`, **Only select repositories > ai-daily-news-digest**, **Actions: Read and write**, and automatic **Metadata: Read-only**. Other account/repository permissions should be off. Actions write is required to dispatch workflows; GitHub does not restrict this token to just one workflow or to dispatch alone. It can access more Actions resources than the monitor token.
3. The **Google monitor** token should be a different token with the same one-repository selection, **Actions: Read-only**, and automatic **Metadata: Read-only**. It does not need Contents, Workflows, Administration, or any account permissions.
4. Use expiring tokens. A **90-day** lifetime is a reasonable maintenance/security balance; set a reminder a week before expiration. Existing expiration dates were not changed by this audit.
5. If a token is correct, no replacement is necessary. If it has excess access, create a replacement with only the permissions above, update the correct service, verify it, and then revoke the old token. Do not revoke a token that is still shared by another active service before migrating that service.
6. For the scheduler, update the cron-job.org job's `Authorization: Bearer ...` header. Its Test/Run button can trigger an actual digest: it is not a harmless credential check. To avoid sending mail, inspect the token permissions and read-only workflow API access, then observe the next scheduled run; a read-only API check alone does not prove dispatch write permission.
7. For the monitor, replace **GITHUB_TOKEN** under Apps Script **Project Settings > Script properties**. Run **inspectDigest** to check read access without sending email; do not run **checkDigest** manually for this review. Review the execution result and confirm the existing hourly trigger remains configured.
8. Review [classic tokens](https://github.com/settings/tokens), [authorized OAuth apps](https://github.com/settings/applications), and [installed GitHub Apps](https://github.com/settings/installations) for obsolete access. Revoke only entries you recognize as unused. Ordinary account sign-in and development access are not automatically replaced by the two service tokens above.

If an old token has been exposed, replace/revoke it rather than only deleting its visible copy. Share only permission names, repository selection, and expiration dates when asking for help.

## Maintaining the action allowlist

When adding an action, review its source and permissions, pin its full verified commit SHA, then update `.github/allowed-actions.json` and **Settings > Actions > General > Actions permissions** together. Do not disable the SHA requirement to make an update pass. Existing action version updates stay within the four allowed repositories. The repository policy is live GitHub configuration; committing the JSON file alone does not apply settings.

## Verification and limits

Run `python -m unittest discover -s tests -v` and `node tests/test_google_apps_script.cjs`. Workflow access regression tests verify checkout credential removal, full action pins, allowlist coverage, read-only permissions, restricted explicit token exposure, and absence of service secrets in automatic tests.

Local verification passed 89 Python tests and seven mocked monitor checks. The history check inspected 138 tracked text objects without matching configured local credentials or the key patterns checked; no `.env` file is tracked.

A local history check compares tracked text objects against configured local credential values and common GitHub/Groq/Google key patterns, reporting only file/object locations, never values. This cannot rule out every possible historical, revoked, encoded, or third-party credential. No account token was rotated and no test email is required for these checks. Hosted regression tests verify allowed actions can run; the live digest/SMTP workflow is deliberately not dispatched during this audit.
