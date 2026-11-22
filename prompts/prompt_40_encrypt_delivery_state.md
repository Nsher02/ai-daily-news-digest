# Encrypt delivery state and safely remove plaintext artifacts

## Goal
Protect sender/recipient addresses and prepared messages before public release of this same repository. Keep visibility private and preserve daily email delivery.

## Requirements
- Use authenticated encryption from a maintained cryptographic library and a new dedicated GitHub repository secret. Never print, commit, or reuse SMTP/AI credentials as the key.
- Upload only ciphertext from separate prepared/final staging paths. Authenticate repository/branch/purpose and every file before restore; fail closed on missing keys, corruption or unmigrated plaintext.
- Preserve message bytes, edition IDs, duplicate prevention, failed-run recovery, schedules, SMTP receipts, provider settings and monitor behavior.
- Add an explicit private/main-only maintenance workflow with no SMTP or AI credentials. Back up original legacy archives and migrate the latest trusted state to encrypted artifacts without sending email.
- Before irreversible cleanup, download and authenticate uploaded backup/seed, compare every plaintext archive to the protected original, and abort on new/changed/uncovered records or active runs. Delete only backed-up plaintext state artifacts, never workflow runs, logs or receipts.
- Explain key backup and controlled rotation, migration, verification and failure handling. Keep all previous prompts and design images.
- Run real-crypto, adversarial, recovery/integration and full offline tests; use the required PR/CI/merge-helper process. Configure the secret securely, perform the no-email migration and verified cleanup, and leave repository visibility private.
