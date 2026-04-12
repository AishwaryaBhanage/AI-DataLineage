# Test Scenario 5 — dbt Cloud URL + Jobs + Usage pages

**Your API key**: `dl_e9a513b87aaf115bdf00c5fa`
**What you're testing**: The full app experience — multiple features across different pages

## Part A — File upload (like the other scenarios)

1. Open the app URL → Settings → paste your API key → Save
2. Debug page → upload `manifest.json` + `run_results.json` → Analyze
3. Verify you see a result

## Part B — Try the dbt Cloud URL field

1. On the Debug page, switch artifact source to **"dbt Cloud"**
2. In the **"dbt Cloud URL"** field, paste this fake URL:
   ```
   https://cloud.getdbt.com/deploy/12345/projects/67890/jobs/111
   ```
3. Check: does a green **"Detected: Account 12345 · Project 67890 · Job 111"** chip appear?
4. (Don't click Analyze — this is a fake URL so it won't work. Just test the URL parsing.)

## Part C — Check the Jobs page

1. Click **"Jobs"** in the sidebar
2. You should see your analysis from Part A listed with:
   - Job ID
   - Status: completed
   - Mode: fast
   - Duration in milliseconds

## Part D — Check the Usage page

1. Click **"Usage"** in the sidebar
2. You should see:
   - **Debug runs** count (should be 1 after Part A)
   - **Fast mode** count
   - **HTTP requests** breakdown by endpoint

## Part E — Navigation persistence

1. After running an analysis in Part A (result visible on Debug page)
2. Click **Jobs** in the sidebar → then click **Debug** again
3. **Question**: Is your result still there, or did it disappear?
   (Expected: result should still be visible — we keep it in memory during navigation)
4. Now **refresh the browser** (Cmd+R / F5)
5. **Question**: Is the result still there?
   (Expected: result should disappear after refresh — that's intentional)

## Feedback I need from you

1. Did the file upload work smoothly? Any confusing steps?
2. Did the dbt Cloud URL parser correctly extract the IDs?
3. Did the Jobs page show your analysis?
4. Did the Usage page show correct counts?
5. Did results persist across navigation but clear on refresh?
6. Which page felt the most useful? Which felt unnecessary?
7. Rate the overall experience 1-10
