Implement a private Google Apps Script webpage alongside the existing email digest, using a branch and PR in the current private repository.

1. IMPLEMENT
   - Read existing main-branch digest artifacts with a dedicated Actions-read token; do not alter email delivery, schedules, or the monitor.
   - Require the deploying owner's Google identity, use an owner-only deployment manifest, keep tokens server-side, and expose only display data. No public upload endpoint, mail/Drive scope, new account, or purchased domain.
   - Show edition date, summary quality, sources, archive selection, refresh, stale/fallback notices, and optional bounded user cache. Preserve a readable prior edition where possible without pretending old content is current.
   - Validate artifact origin and redirects, never forward a GitHub token to storage, and render only escaped/text-node content. Keep credentials, recipient metadata, delivery state, and raw HTML out of the client.

2. VERIFY AND GUIDE
   - Test privacy gates, artifacts, redirect credential handling, cache/error behavior, and client rendering. Add offline checks to CI and inspect the layout using synthetic preview data.
   - Provide exact manual steps for the separate Apps Script project, files, identity/token properties, authorization, Only myself deployment, and phone/Mac/private-window verification. Never request the token value in chat.
   - Preserve images/prompts. Follow CONTRIBUTING.md: branch, PR, current-head tests, checked merge. Keep email unchanged until the deployed page is confirmed working. Do not send test email or dispatch delivery workflows.
