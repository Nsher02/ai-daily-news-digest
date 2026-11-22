# Audit the repository before public release

## Goal
Review current source, all available Git history and prompts, and retained Actions logs/artifacts for credential exposure, private information and public-contribution trust-boundary risks. Keep the repository private and email delivery unchanged.

## Requirements
- Fetch available branches/tags/PR refs and inspect historical blobs and commit metadata. Inspect every retained workflow attempt log and artifact available at the audit snapshot; state counts and limitations.
- Never print, reuse or validate discovered credentials. Keep downloaded private records outside the repository. Distinguish saved secret references, dummy fixtures and public identifiers from credentials.
- Preserve existing prompts and design images. Document personal-author identity and reference-redistribution decisions without reproducing private values.
- Fix verified recovery-artifact provenance issues at the restore boundary and prevent raw provider/feed exception messages from entering logs. Preserve trusted failed-run recovery, duplicate prevention, email content, SMTP settings, providers and schedules.
- Do not delete remote records, rewrite history, rotate credentials, change visibility, send emails or dispatch delivery. Describe unresolved artifact privacy and a safe public-portfolio alternative.
- Run focused adversarial/legitimate controls and the full offline suite. Publish safe fixes through the existing tested PR and merge-helper process.
