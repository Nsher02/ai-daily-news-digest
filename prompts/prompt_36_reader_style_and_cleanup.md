# Clean up private reader debugging and match the email design

## Goal
Remove temporary identity debugging and bring the private Apps Script reader into line with the existing Apple News-inspired digest email.

## Requirements
- Preserve the owner-only gate, monitor, credentials, trigger, email delivery, prompts, and design images.
- Distinguish a missing Index HTML template from an identity denial using safe static errors.
- Match the email column width, header gradient, masthead, typography, section rules, and grey disclosure footer. Keep reader controls usable on phones.
- Continue rendering safe text nodes and HTTP/HTTPS links; do not expose raw email HTML or load remote images.
- Document precisely which temporary diagnostics to remove in the live project and how to update its existing private deployment.
- Run offline reader, monitor, and Python checks. Publish through a tested PR and the merge helper. Do not send email or dispatch delivery.
