Automatically verify changes to the digest without sending email or calling live AI services. Inspect the existing tests and workflow before implementation.

1. AUTOMATIC CHECKS
   - Add a separate GitHub Actions workflow for pushes, pull requests, and manual test runs.
   - Run the existing Python regression suite and mocked Google Apps Script monitor tests. Validate the monitor's syntax and JSON manifest.
   - Match the production Python version. Pin external actions to verified full commit hashes and grant only read-only repository access.
   - Do not provide email or AI secrets, run the daily delivery workflow, or send test emails. Keep test concurrency separate from delivery concurrency.
   - Bound execution time and cancel superseded test runs.

2. VERIFY AND DOCUMENT
   - Run the checks locally, validate the workflow, and document where GitHub shows results.
   - Preserve all existing prompts and design images. Publish only with session authorization and verify the hosted test result when published.
