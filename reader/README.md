# Private digest reader — Google Apps Script

A free, owner-only bookmarked webpage that reads existing digest artifacts from the private GitHub repository. Email delivery, its schedule, and the missing-email monitor are unchanged. No new account, domain, public upload endpoint, Drive access, email permission, or AI call is required to read the page. No new time-driven trigger is needed: the page reads saved editions when opened or refreshed.

## 1. Create a separate Google project

Open https://script.google.com/ under the Google account you want to use on both phone and Mac. Create a new project named **AI Daily News Digest — Private Reader**. Keep the project private and separate from the monitor. Project editors can access its Script properties, so do not share editor access.

## 2. Copy three files

1. In the editor, replace **Code.gs** with the contents of [Code.gs](Code.gs).
2. Use the **+** beside Files > **HTML**. Name it **Index** and replace its contents with [Index.html](Index.html).
3. Open **Project Settings** (gear). Enable **Show “appsscript.json” manifest file in editor**. Return to Editor, select **appsscript.json**, and replace its contents with [appsscript.json](appsscript.json).
4. Save all files. The manifest requests only external HTTP requests and your basic account email for the owner check. It requests no permission to read or send mail or access Drive. It specifies web-app access `MYSELF` and execution as `USER_DEPLOYING`.

## 3. Configure identity and read-only access

Create a separate [fine-grained GitHub token](https://github.com/settings/personal-access-tokens/new) named **AI Daily News Digest — Private Reader**:

- Resource owner: **Nsher02**.
- Repository access: **Only select repositories > ai-daily-news-digest**.
- Repository permissions: **Actions: Read-only** and automatically included **Metadata: Read-only**. No Contents, Workflows, Administration, or write permissions.
- Choose a finite expiration and a renewal reminder. A 90-day expiry is reasonable if you are comfortable renewing quarterly.

In the new Google project, open **Project Settings > Script properties** and add:

| Property | Value |
| --- | --- |
| `OWNER_EMAIL` | The Google account email you are using to own and deploy this project—not necessarily the iCloud recipient address. |
| `GITHUB_TOKEN` | The new read-only token. |

Save the properties. Keep the token here only, not in the source, GitHub issues, screenshots, a URL, or chat. Do not change your existing monitor token or add this token to GitHub repository secrets.

## 4. Perform the safe setup check

In the editor select **inspectReader** and click **Run**. Review Google's authorization request; the expected permissions are basic account email and external connections. The developer/project should be your own. If the account, project, or requested permissions differ, stop and review them.

A successful execution logs only an edition date, summary quality, and stale/cache flags. It does not print the token, recipient, or raw digest, and sends no email. A stale date means the saved digest is older than today's Chicago date; it does not prove email failed. A `raw_headlines` or `partial_pass_2` result describes summary completeness.

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
node --check < reader/Code.gs
python3 -m json.tool reader/appsscript.json
```

The privacy checks simulate owner and unauthorized identities, API failures, cache fallback, invalid selections, expired/other-branch artifacts, malformed saved data, approved redirects, private-only manifest settings, and exclusion of recipient/token/raw HTML from browser data. The existing Python regression suite and monitor checks remain in CI. None of these checks sends mail.

## Stop the page without affecting email

Archive the reader's web-app deployment and revoke only its dedicated GitHub token. Leave the digest workflow and monitor project unchanged.
