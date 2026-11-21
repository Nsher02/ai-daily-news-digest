# Remove web hosting and keep email delivery

## Goal
Return the repository to email-only digest delivery by removing all web-reader and Safari-test code. Preserve the optional standalone missing-digest monitor.

## Requirements
- Remove reader server/client code, manifests, shared-monitor copy, hosting guides, and reader-only tests and CI steps.
- Keep the standalone monitoring code and its offline scenarios. Explain what the monitor checks, its limits, and why it is useful independently of GitHub Actions.
- Update README and monitor documentation with exact live deployment removal and standalone-monitor restoration steps. Preserve the existing hourly cadence and daily state; do not invoke the alert-sending handler.
- Preserve every existing prompt and original design image. Do not change daily delivery, AI providers, SMTP configuration, scheduling workflows, or secrets.
- Run the complete offline regression suite, monitor checks, syntax/manifest checks, and applicable workflow lint. Do not send email or dispatch delivery.
- Keep the repository private. Publish on a codex branch, open a PR, and merge only through the merge helper after the current PR commit passes Offline regression tests.
