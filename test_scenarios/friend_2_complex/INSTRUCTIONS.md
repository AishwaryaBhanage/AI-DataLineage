# Test Scenario 2 — Complex multi-error query (6 errors)

**Your API key**: `dl_ed7be0d983e411ec5eb4b440`
**What you're testing**: LLM's ability to find multiple errors in one query with CTEs and window functions

## Steps

1. Open the app URL in your browser
2. Go to **Settings** → paste your API key above → Save
3. Go to **Debug** page
4. Keep **"Analyze"** mode selected
5. Upload the `manifest.json` and `run_results.json` from this folder
6. Click the **"Advanced options"** toggle at the bottom of the form
7. In **"Model to debug"**, type: `customer_lifetime_metrics`
8. Click **"Run analysis"**

## What you should see

The AI should find **6 distinct errors** in one query:

| # | Error | What happened |
|---|-------|--------------|
| 1 | `amount` | Should be `amount_total` (renamed in staging) |
| 2 | `price` | Dropped during staging — doesn't exist anymore |
| 3 | `customer_name` | Should be `full_name` (renamed in staging) |
| 4 | `email_address` | Typo — doesn't exist anywhere |
| 5 | `phone_number` | Exists in raw data but dropped for PII compliance |
| 6 | `membership_level` | Should be `loyalty_tier` |

## Feedback I need from you

1. How many of the 6 errors did the AI find? (Check the "affected columns" list)
2. Did it explain WHY phone_number was dropped (PII compliance)?
3. Was the corrected SQL provided? Did it look correct?
4. Did the lineage graph show 5+ nodes?
5. How long did the analysis take?
6. Rate the overall experience 1-10
