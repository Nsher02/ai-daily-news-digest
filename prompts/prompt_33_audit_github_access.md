Audit GitHub repository access and token permissions, fix verified issues, and preserve daily delivery.

1. AUDIT AND HARDEN
   - Inspect repository visibility, collaborators, deploy keys, webhooks, workflow defaults, allowed actions, credential exposure, and dependency-alert settings without printing secrets.
   - Restrict action sources and require full SHA pins. Disable persisted checkout credentials and scope explicitly supplied workflow credentials to the steps that need them.
   - Keep existing read-only job permissions and separate AI/SMTP secrets. Enable free dependency alerts and reviewable update PRs without automatic merges or paid feature enrollment.
   - Inspect external-token metadata where available; otherwise document exact manual review steps for one-repository scheduler Actions write and independent monitor Actions read tokens, expiration, rotation and safe validation. Do not revoke active credentials blindly or broaden the audit credential to work around unavailable features.
   - Preserve privacy, original images, prompts, state artifacts, and delivery behavior.

2. VERIFY AND PUBLISH
   - Add offline access-boundary regression checks, run the full existing test suite, validate workflows, and inspect credential patterns without printing values.
   - Document observed findings and API/plan/account limitations accurately. Distinguish GitHub's live settings from version-controlled policy documentation.
   - Commit and push the changes, verify automatic tests run under the tightened live policy, and guide the user through manual settings. Do not dispatch the daily digest, send a test email, or make paid plan changes.
