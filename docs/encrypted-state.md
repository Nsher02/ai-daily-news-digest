# Encrypted delivery-state artifacts

The digest still prepares and sends the same email through the same providers, schedule and SMTP configuration. Encryption changes storage between runs, not the message or retry policy. Keep the repository private until migration and cleanup are verified and the other publication-audit decisions are resolved.

## Storage and key

- `DIGEST_STATE_KEY` is a dedicated GitHub Actions repository secret containing a generated Fernet key. It is independent of SMTP, Gemini, Groq and GitHub access tokens. Never commit or paste it in chat.
- `cryptography`'s high-level Fernet recipe provides authenticated encryption (AES-CBC plus HMAC), random encryption and tamper detection. The authenticated envelope binds the version, repository name, branch and purpose. No custom cipher or password-derived key is used.
- Each normal artifact contains **only `state.enc`**. The encrypted payload preserves the original bytes of prepared.json, history.json and quality.json, including recipient, sender, message body, edition status and IDs. Plaintext remains only in the authorized runner's working state while needed for delivery.
- Prepared and final ciphertext have separate staging paths. Uploads never use a JSON wildcard. Encryption failure cannot fall back to plaintext upload. Restore authenticates every member before writing state and stops on missing/wrong keys or corrupted ciphertext.
- The key is supplied only to restore and encryption steps. AI preparation, SMTP sending, dependency installation and PR tests do not receive it. API origin checks still precede artifact downloads.
- Artifact names, size, creation time and workflow metadata remain visible to repository readers. Encryption does not hide Actions logs or Git history.
- State artifacts and the migration backup retain the existing seven-day expiry. Keep a secure backup of the key; GitHub does not let you retrieve its saved value. Do not overwrite or rotate it while retained artifacts depend on it. Rotation or renaming the repository/branch needs a planned decrypt/re-encrypt migration with the previous key/context; it is not automatic. A lost key fails closed rather than resetting history.

## Add the secret manually, if not already configured

1. Generate a key locally with the installed dependency, and save it directly to a private file or password manager. Do not use an online key generator or reuse a password.
2. Open **GitHub repository > Settings > Secrets and variables > Actions > New repository secret**.
3. Name it **DIGEST_STATE_KEY** and enter the generated key as its value. Save.
4. Keep a password-manager backup. Do not share the value, use a repository variable instead, overwrite an existing key without a rotation plan, or revoke other credentials.

The implementation session can also generate and set this secret through the authenticated GitHub CLI, passing the value on standard input rather than a command-line argument or chat. If that was done, do not create a replacement; back up the owner-only local key file supplied in the session. Temporary files are not durable password-manager storage.

## First migration — no email or AI calls

Normal restore deliberately rejects old plaintext artifacts. Configure the key, merge the tested change, and complete this migration **before the next normal delivery run**. The repository must remain private. No daily delivery dispatch is required.

1. Run **Actions > Encrypt legacy delivery state (no email) > Run workflow**, selecting **main**. This is `state-maintenance.yml`, not the daily delivery or Groq workflows.
2. The maintenance job has read-only Actions/Contents permissions and no SMTP or AI credentials. It shares the normal delivery concurrency group. It also refuses to proceed if other delivery/maintenance runs are active or queued.
3. It verifies old artifact origins, encrypts a backup of the original archive bytes, and preserves the latest trusted state in a separate encrypted seed. It verifies a local decrypt round-trip before uploading.
4. A successful run produces **digest-state-encrypted-migrated-RUN-ATTEMPT** (`state.enc`) and **digest-legacy-encrypted-backup-RUN-ATTEMPT** (`legacy-backup.enc`). Do not delete old artifacts if either upload or the run fails.
5. On the next normal run, restore selects the latest trusted encrypted state from the delivery workflow or this exact manually dispatched maintenance workflow. Failed legitimate delivery records remain recoverable. Nothing changes SMTP-acceptance receipts, ambiguous-send handling or cross-day deduplication.

If the maintenance workflow cannot start, check the already-reviewed action allowlist, key setup and repository privacy. Do not relax permissions or dispatch the email workflow as a test. If another run appears, wait for it to finish and repeat maintenance.

## Verified plaintext cleanup

Run cleanup locally using the same key in `DIGEST_STATE_KEY` and an authenticated GitHub CLI. Do not type the key into shell history; load it from your protected key file/password manager through a trusted local method.

```sh
.venv/bin/python state_maintenance.py cleanup --repo Nsher02/ai-daily-news-digest --run-id MIGRATION_RUN_ID
```

The default is a **read-only plan**. It downloads the uploaded encrypted backup and seed, verifies their origin and successful maintenance run, authenticates both, and compares the seed to the protected snapshot. Every plaintext archive slated for deletion must match its backed-up original bytes, ID, name and hash. New, changed or unbacked artifacts stop cleanup before deletion.

Only after reviewing that plan, explicitly authorize deletion:

```sh
.venv/bin/python state_maintenance.py cleanup --repo Nsher02/ai-daily-news-digest --run-id MIGRATION_RUN_ID --delete
```

The task's implementation session may perform this already-authorized cleanup after verification. Cleanup rechecks privacy, active/queued jobs and the plaintext inventory immediately before deletion. It deletes **only the verified legacy state artifacts**, never workflow runs, logs, jobs or SMTP-acceptance receipts. It retains the encrypted seed and backup, and checks that no unexpired legacy state artifacts remain. On a partial API failure the uploaded encrypted backup still covers deleted records; rerunning checks the remaining subset. Keep the repository private on any unexpected result.

An expired artifact is no longer downloadable and is excluded from cleanup. Encrypted backups also expire after seven days; the live state is carried forward by daily encrypted artifacts. Do not delete or reset live delivery state merely to resolve a key/authentication error.

## Verification and remaining release work

Tests use generated fixture keys, real encryption/decryption and mocked GitHub/SMTP. They cover tampering, wrong keys, cross-repository/branch/purpose replay, traversal/mixed archives, all-member validation, original message preservation, accepted-send duplicate suppression, migration backup fidelity and deletion guards. A successful live maintenance run and downloaded/decrypted backup check verify hosted storage without sending email.

After migration and cleanup, independently inspect the latest artifact ZIP members (ciphertext files only), verify the repository is still private and the workflow/SMTP receipts remain, and observe the next normally scheduled delivery. No test email is required. This closes the plaintext-artifact issue but does not decide whether to publish the academic author email or third-party reference images identified in [the publication audit](publication-audit.md).
