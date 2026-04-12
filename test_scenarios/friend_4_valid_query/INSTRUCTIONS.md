# Test Scenario 4 — Valid query detection

**Your API key**: `dl_f5ec9e408049480e441b31a0`
**What you're testing**: Can the system correctly identify a WORKING query as valid?

## Steps

1. Open the app URL in your browser
2. Go to **Settings** → paste your API key above → Save
3. Go to **Debug** page
4. Upload the `manifest.json` and `run_results.json` from this folder
5. Click the **"Advanced options"** toggle
6. In **"Model to debug"**, type: `stg_orders`
7. Click **"Run analysis"**

## What you should see

Since `stg_orders` is a **working model** with no errors:

- A **green "Query is valid"** banner (NOT a red failure banner)
- Root cause should say something like "No errors found" or "Query appears valid"
- No corrected SQL (nothing to fix)
- The lineage graph should still render correctly

## Why this test matters

Most debugging tools only work when things are broken. A good tool should
also correctly confirm when things are fine. If the AI reports a false
error on a valid query, that's a bug.

## Feedback I need from you

1. Did you see a GREEN banner (not red)?
2. Did the AI correctly say the query is valid?
3. Did it try to "fix" anything that wasn't broken? (It shouldn't)
4. Was the confidence score reasonable (should be 0.80+)?
5. Rate the overall experience 1-10
