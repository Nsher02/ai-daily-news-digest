Improve visibility into email delivery while preserving the current iCloud SMTP configuration. Inspect send_email, Actions summaries, send_window.py, and receipt consumers first. Implement this prompt only when explicitly asked to execute it.

1. DELIVERY RECORDS
   - Distinguish prepared, SMTP-accepted, confirmed-delivered, bounced, failed, and unknown outcomes where evidence supports them. Current SMTP acceptance confirms server acceptance only.
   - Attach a stable edition identifier and a standards-compliant Message-ID. Record safe timestamps and identifiers in durable run metadata without publishing credentials or email body contents.
   - Preserve existing SMTP-accepted receipt compatibility and backup suppression. A missing downstream delivery confirmation must not automatically trigger another digest email.
   - Report exactly which delivery evidence is available with the current transport. Mark final inbox delivery unknown when it cannot be observed.
   - Describe the future integration for provider message IDs and authenticated delivery/bounce events. Defer provider-specific implementation, endpoints, and activation until a provider is chosen. Treat receiving-server acceptance separately from inbox placement or reading.

2. VERIFY AND DOCUMENT
   - Test successful SMTP acceptance, SMTP rejection, malformed metadata, receipt compatibility, and unknown downstream status using mocks.
   - Document current observability and the provider migration dependency. Do not create a Resend account, change sender configuration, send email, deploy a webhook, commit, or push without separate authorization.
