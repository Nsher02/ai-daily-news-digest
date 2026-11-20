# Safari access test in the existing monitor and reader project

This tests whether a content-free page can open in normal Safari with multiple Google accounts. It does not implement a working login or password, and does not make digest content public. It uses the same Apps Script project, Google account, read-only GitHub token, and private repository. No new service or account is needed.

## What changes and what stays the same

- `Reader.gs` adds only the static `?view=safari-test` route. The normal reader and every digest-data request still require OWNER_EMAIL to match Google's active identity. No effective-user fallback is allowed.
- `SafariTest.html` contains disabled password controls. It has no scripts, forms, remote assets, digest content, secrets, network calls, or mail action.
- `Monitor.gs` is a shared-project copy of the standalone monitor with **only its entry-point names and header comment changed**. `checkDigest` becomes `checkDigest_`; `inspectDigest` becomes `inspectDigestSetup_`. Google's browser RPC cannot call functions ending in an underscore. The receipt rules, deadline, alert handling, daily state, and locking are unchanged. Automated checks enforce source parity and run both variants through the same scenarios.
- **The existing hourly trigger must be retargeted to `checkDigest_`.** Do not leave a trigger pointing at a removed function or create a second hourly trigger. Its cadence, deploying account, failure notifications, and monitoring purpose must stay the same. This is a necessary handler-name migration, not a new monitoring schedule.
- The existing `/exec` reader deployment stays **Only myself**, pinned to its current version. The new test deployment uses a new version containing the safeguards. Never change an old unguarded version to Anyone.
- The public test can still consume Google execution quota. A one-project deployment shares the monitor's permissions and quota even though its private monitor functions cannot be invoked by browser RPC. Archive the test after collecting results.

## 1. Prepare the live files before creating any public deployment

Do this while signed into the owner account in the Apps Script editor. Do not edit any deployment access yet. Keep local copies of the current live Code.gs and Reader.gs as a rollback backup outside the live project. Note the existing trigger's hourly settings.

1. Replace **all of Code.gs** with [Monitor.gs](Monitor.gs). **Do not add it as a second monitor file**; duplicated constants or functions will break the project. The standalone file in monitoring/ is preserved for projects without public web deployments.
2. Replace **all of Reader.gs** with [Reader.gs](Reader.gs). Leave **Index.html** unchanged.
3. Add **+ > HTML**, name it **SafariTest**, and paste [SafariTest.html](SafariTest.html). Google adds `.html`.
4. Keep the combined [appsscript.json](appsscript.json), all Script Properties, and private editor sharing unchanged. No new password, token, permission scope, or property is needed.
5. Remove old temporary debugging functions such as `inspectReaderIdentity()` and any duplicate or old public `checkDigest()` / `inspectDigest()` definitions elsewhere. The only `.gs` files for this tested shared setup are Code.gs (the new monitor contents) and Reader.gs. If there is other custom server code, review it before publishing: every extra public function needs its own authorization guard or a private name. No `doPost` or API-executable deployment is needed.
6. Save, then open **Triggers**, edit the existing hourly monitor trigger, and change its function to **checkDigest_**. Keep **Time-driven > Hour timer > Every hour**, its owner account, and its existing failure notifications. Confirm there is exactly one hourly monitor trigger. **Do not click Run on checkDigest_**; it can send a real monitoring alert.

If Google does not offer the private handler in the trigger editor, **stop before publishing**. Restore the saved Code.gs and Reader.gs so the existing checkDigest trigger continues working, and report what the trigger editor shows. Do not add an unguarded public wrapper as a workaround. Trigger selection and execution must be verified live; mocked tests cannot establish Google's UI behavior.

## 2. Perform read-only checks

Select **inspectReader** and click **Run**. This uses the existing owner identity check and reads saved digest data without sending mail or changing monitor state. It should log only date/quality metadata.

For a monitor-only read check, if the editor offers **inspectDigestSetup_**, run that, never checkDigest_. Its return and logs are metadata only. If private functions are not selectable, inspectReader is enough for this access test; don't create a public unguarded diagnostic wrapper. After the next normal hourly execution, confirm **checkDigest_** completed successfully in Executions. Do not reset LAST_CHECK_DATE or force an extra monitoring check.

## 3. Create a second deployment for the test only

1. Choose **Deploy > New deployment > gear > Web app** in the same project.
2. Description: **Safari blank access test — no digest content**.
3. **Execute as: Me**.
4. **Who has access: Anyone**, meaning visitors do not need to sign into Google. Do not use **Anyone with a Google account** for this test. If the anonymous option is unavailable, stop and report that restriction.
5. Deploy a **new version containing the safeguarded files**. Copy its new Web app `/exec` URL. Do not change the existing reader deployment or republish an older version as Anyone.
6. Append **?view=safari-test** to the new URL. If Google has already appended a query, use **&view=safari-test** instead. Do not add email, password, or token parameters.
7. Reopen Manage deployments and verify the original reader is still **Only myself**, and only the newly created safeguarded test deployment is **Anyone**.

## 4. Test normal Safari and signed-out access

- Open the new `/exec?view=safari-test` address in normal Safari with all your existing Google accounts still signed in. Expected: **Digest login test** and disabled controls.
- Open that same address in a Safari Private Window without signing into Google. Expected: the same static page.
- In the signed-out window, remove `?view=safari-test`. Expected: **Access denied. Sign in with the reader owner account.** No headlines, summaries, archive, or subject should appear. The test route is intentionally the only anonymous page.
- Do not enter a password; none is configured. Report which windows show the test screen and which still show Google's Drive error. Even an anonymous deployment may still hit Google's account-routing bugs; a successful live test is needed before choosing the next authentication design.

The page alone has no digest access, but backend safety does not depend on hiding buttons: digest-data methods check the active owner before accessing cache or GitHub, and mail-capable monitor helpers are private to browser RPC. Google's deployment executes as the owner, so `getEffectiveUser()` is deliberately not an authentication check.

## 5. Finish or roll back

After the results are recorded, **Deploy > Manage deployments > select the Safari test deployment > Archive**. Keep the original private reader deployment, properties, and hourly checkDigest_ trigger. This removes the anonymous web surface without stopping the monitor. No email migration or password system has been activated.

To undo the handler migration too: first archive every anonymous test deployment, restore the backed-up Code.gs and Reader.gs, then retarget the same hourly trigger back to **checkDigest**, preserving its hourly settings. Do not keep both monitor files or both hourly triggers.

Repository updates alone do not update live Apps Script code, deployments, or triggers. Offline tests establish the mocked function surface and behavior; they do not verify real Safari routing, Google permissions, or the hosted trigger.

Sources: [Google private server functions](https://developers.google.com/apps-script/guides/html/communication#private_functions), [Session identity limitations](https://developers.google.com/apps-script/reference/base/session), [deployment versions](https://developers.google.com/apps-script/concepts/deployments).
