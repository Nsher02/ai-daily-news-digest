# Safeguard the shared Apps Script project and test Safari access

## Goal
Prepare a content-free public Safari access test in the existing monitor and reader Apps Script project. Keep the GitHub repository private and email delivery and hourly monitoring behavior unchanged.

## Requirements
- Preserve the existing owner-only reader and its identity gate on every data request.
- Add a separate static Safari test route with disabled login controls; no password implementation, credentials, digest data, network calls, or email actions.
- Keep the default manifest private. Document a separate anonymous test deployment without changing the existing reader deployment.
- Provide a shared-project monitor variant whose entry points end in an underscore and cannot be called from browser RPC. Keep its implementation identical to the standalone monitor apart from entry-point names and comments.
- Explain the required manual retargeting of the existing hourly trigger to the private handler, preserving its frequency, owner, and alert settings. Never run the sending handler for setup.
- Inventory public functions and test anonymous and wrong-account calls, forged request data, cache access, source and manifest privacy, and monitor parity offline.
- Keep all prompts and original design images. Publish through a codex branch, tested PR, and merge helper. Do not send email or dispatch delivery.
