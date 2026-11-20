# Private digest reader — Google Apps Script

A free, owner-only bookmarked webpage that reads existing digest artifacts from the private GitHub repository. Email delivery, its schedule, and the missing-email monitor are unchanged. No new account, domain, public upload endpoint, Drive access, email-reading permission, or AI call is required to read the page. No new time-driven trigger is needed: the page reads saved editions when opened or refreshed.

## 1. Reuse and rename your monitor project

Open https://script.google.com/ and open your existing **AI Daily News Digest Monitor** project. Click its title and rename it **AI Daily News Digest — Monitor & Reader**. This is the same project, not a new account or subscription. Keep editor access private.

Preserve the existing **Code.gs** monitor code, **GITHUB_TOKEN**, **ALERT_EMAIL**, **LAST_CHECK_DATE**, **LAST_CHECK_STATUS**, and the existing hourly **checkDigest** trigger. Renaming the project does not require a new token or replacement trigger.

## 2. Add reader files without replacing the monitor

1. In the editor use **+ > Script**. Name the new file **Reader** and paste [Reader.gs](Reader.gs) into it. Leave the existing monitor **Code.gs** unchanged.
2. Use **+ > HTML**, name it **Index**, and replace the new file's contents with [Index.html](Index.html).
3. In **Project Settings** enable **Show “appsscript.json” manifest file in editor**. Return to Editor and replace the manifest with [appsscript.json](appsscript.json).
4. Save. This combined manifest retains external requests and **sending email**, which your monitor already needs, and adds basic account email for the reader's owner check. It requests no inbox-reading or Drive permission. The web-app setting is **MYSELF**, executed as the deploying owner.

The shared project retains its ability to send monitoring alerts; the reader itself contains no mail-sending operation. The two functions share a project and authorization grant, so they are not isolated from one another. Do not change deployment access to Anyone.

## 3. Add only the owner identity property

Open **Project Settings > Script properties**. Keep all existing properties and add:

| Property | Value |
| --- | --- |
| `OWNER_EMAIL` | The exact Google account email owning and deploying this project—not necessarily your iCloud recipient address. |

Reuse the monitor's existing **GITHUB_TOKEN**, already restricted to this repository with **Actions: Read-only** and automatic Metadata read access. No new token or GitHub repository secret is needed. The reader does not use ALERT_EMAIL or change monitor state. Never share the token in chat, source files, screenshots, or URLs.

## 4. Perform the safe setup check

In the editor select **inspectReader** and click **Run**. Review Google's authorization request; the expected permissions are basic account email, external connections, and the existing monitor’s email-sending permission. The developer/project should be your own. If the account, project, or requested permissions differ, stop and review them.

Select **inspectReader**, not checkDigest, for this setup. A successful execution logs only an edition date, summary quality, and stale/cache flags. It does not print the token, recipient, or raw digest, and sends no email. A stale date means the saved digest is older than today's Chicago date; it does not prove email failed. A `raw_headlines` or `partial_pass_2` result describes summary completeness.

If access is denied, check the exact Google email in OWNER_EMAIL, the account selected in the editor, and that the manifest is saved. Blank or non-owner identities are rejected rather than allowed through. Do not weaken the identity check to work around an account mismatch.

## 5. Deploy privately

1. Click **Deploy > New deployment**.
2. Click the deployment-type gear and choose **Web app**.
3. Set **Execute as: Me**.
4. Set **Who has access: Only myself**. Do not choose Anyone or Anyone with a Google account.
5. Click **Deploy** and copy the **Web app URL** ending in `/exec`.

The manifest and code are both restrictive: Google controls the private deployment, and each data request independently checks the signed-in user's email. The URL is not a secret-link substitute for authentication. There is no public `doPost` or upload API.

## 6. Verify before changing email

- Open the `/exec` URL on your Mac while signed into the owner Google account. Confirm the edition date, summaries, source links, Refresh, and Saved editions menu.
- Open the same URL on your iPhone in Safari, sign into the same Google account, and bookmark it or add it to the Home Screen. Check narrow-screen readability and source-link behavior.
- Open it in a signed-out/private browser window. It should require Google sign-in and must not display a digest anonymously. If possible, verify a different Google account cannot read it either.
- Keep email delivery and the existing monitor active. Report whether the page works on both devices before considering any email migration. No test email is needed.

For later code updates, copying a new file into the editor does not update an existing deployment automatically. Save, then **Deploy > Manage deployments > Edit (pencil) > Version: New version > Deploy**. Reuse that deployment to retain the bookmark URL and confirm its access remains Only myself.

## Availability, retention, and privacy

- The reader uses the existing prepared/final artifacts; it can show content saved before SMTP delivery even when the email bounces. It cannot display a new edition that never reached the preparation/upload stage.
- It groups prepared/final artifacts by run, prefers final state, and displays up to 20 unexpired editions from recent artifact pages. Existing artifacts expire after **seven days**. This is a short archive, not permanent storage.
- A failed newest edition can fall back to a previous readable one, visibly labeled. An optional per-user cache requests up to **six hours** and may be evicted earlier by Google. It is a convenience, not a durable archive or outage guarantee. No Google Drive permission is requested.
- Dates use **America/Chicago**, matching the digest. An older date always displays an explicit warning. Full, partial, and headline-only editions are distinguished.
- GitHub API failures, token expiry, Google outages, and quota limits can still interrupt access. Cache fallback does not bypass the owner identity check.
- Only date, subject, summary-quality status, source text and links, and edition-list labels reach the browser. Recipient addresses, raw email HTML, SMTP state, and credentials are excluded.
- All content is rendered with DOM text nodes; stored HTML is never executed. Remote images and tracking assets are not loaded by the reader. Links open only HTTP/HTTPS destinations in a separate tab with opener/referrer protections.
- The GitHub bearer credential goes only to api.github.com. Signed artifact downloads are restricted to approved storage host suffixes and receive no Authorization header. Raw GitHub errors, signed URLs, and credentials are not returned to the browser.
- The project URL and the Google token setup are manual account work. Local mocked/browser checks do not establish that the live Google deployment or phone sign-in has been verified.

## Offline checks

From the repository root:

```sh
node tests/test_private_reader.cjs
node --check < reader/Reader.gs
python3 -m json.tool reader/appsscript.json
```

The privacy checks simulate owner and unauthorized identities, API failures, cache fallback, invalid selections, expired/other-branch artifacts, malformed saved data, approved redirects, private-only manifest settings, and exclusion of recipient/token/raw HTML from browser data. The existing Python regression suite and monitor checks remain in CI. None of these checks sends mail.

## Stop the page without affecting email

Archive only the web-app deployment. Keep the shared GITHUB_TOKEN and checkDigest trigger, which the monitor still uses. Leave the digest workflow unchanged.

## Clean up setup diagnostics and match the email design

After the page works, replace the entire live **Reader.gs** with this repository's version. This removes the temporary `inspectReaderIdentity()` function, its call in `doGet()`, and the temporary staged `stage` / `errorType` / `reason` logging. Keep the permanent owner check and `inspectReader()` setup check. The production `doGet()` distinguishes an owner denial from a missing HTML template without logging account identities or raw errors.

Replace the contents of the existing **Index.html** with the current version here. Create it with **+ > HTML > Index** only if it is missing; Google adds the extension. Keep exactly the HTML template referenced as `Index`. Delete a mistaken duplicate only after confirming it is unused. Do not delete the working template.

Keep the monitor's **Code.gs**, combined **appsscript.json**, all existing Script Properties (including OWNER_EMAIL), and the hourly **checkDigest** trigger. Execution history can remain; no new trigger or token is needed.

Save, then update the existing deployment using **Deploy > Manage deployments > pencil > Version: New version > Deploy**. Confirm **Execute as: Me** and **Only myself**. Open the existing `/exec` bookmark to verify it, including on your iPhone. The `/dev` test page uses saved editor code; an existing `/exec` deployment needs this version update. No email test is needed.

The reader now follows the email's 600px column, black-to-grey header fade, two-line Good Morning masthead, pink Top stories label, serif headlines and top-story summaries, section rules, and full-width #2c2c2c disclosure area. Reader controls and edition status remain above the content. Stored email HTML is still excluded, and remote thumbnails remain omitted to avoid loading third-party image assets.
