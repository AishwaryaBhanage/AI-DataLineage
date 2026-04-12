# Test Scenario 1 — Simple column rename error

**Your API key**: `dl_385c5eacd16657ddd2b944b7`
**What you're testing**: Basic fast-mode analysis on a simple 1-error query

## Steps

1. Open the app URL in your browser
2. Go to **Settings** → paste your API key above → Save
3. Go to **Debug** page
4. Keep **"Analyze"** mode selected (left option)
5. Keep **"Upload files"** as the source
6. Drag and drop these files:
   - `manifest.json` from this folder → into the left drop zone
   - `run_results.json` from this folder → into the right drop zone
7. Click **"Run analysis"**
8. Wait ~4 seconds for the result

## What you should see

- A **red "Pipeline failure detected"** banner showing `customer_revenue`
- A **root cause card** saying something about `amount` being renamed to `amount_total`
- A **lineage graph** with 3 nodes (raw_orders → stg_orders → customer_revenue)
- A **corrected SQL** diff showing the fix
- Confidence should be ~95-98%

## Feedback I need from you

1. Did the result appear within 5 seconds?
2. Was the root cause explanation clear and understandable?
3. Did the lineage graph render properly?
4. Any errors or confusing parts in the UI?
5. Rate the overall experience 1-10
