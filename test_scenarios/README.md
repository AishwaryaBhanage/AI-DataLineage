# Beta Test Scenarios

5 test scenarios for 5 beta testers. Each friend gets a different folder
with the same dbt artifacts but different testing instructions.

## Quick reference

| Folder | Friend | API Key | What they test |
|--------|--------|---------|---------------|
| `friend_1_simple/` | Friend 1 | `dl_385c5eacd16657ddd2b944b7` | Simple 1-error analysis (fast mode) |
| `friend_2_complex/` | Friend 2 | `dl_ed7be0d983e411ec5eb4b440` | Complex 6-error query with CTEs + window functions |
| `friend_3_agentic/` | Friend 3 | `dl_b0f56432cce1c27eaa126559` | Agentic (deep analysis) mode — multi-agent ReAct |
| `friend_4_valid_query/` | Friend 4 | `dl_f5ec9e408049480e441b31a0` | Valid query detection — should show green "valid" banner |
| `friend_5_cloud_upload/` | Friend 5 | `dl_e9a513b87aaf115bdf00c5fa` | Full app tour: upload, dbt Cloud URL, Jobs, Usage, navigation |

## What each folder contains

```
friend_N_xxx/
├── manifest.json      ← dbt project structure (all 6 models)
├── run_results.json   ← execution results (2 failures, 4 passes)
└── INSTRUCTIONS.md    ← step-by-step guide for what to test + feedback questions
```

## How to distribute

### Option A — Share the folder directly
Zip each friend's folder and send via email/Slack:
```bash
cd test_scenarios
zip -r friend_1_simple.zip friend_1_simple/
zip -r friend_2_complex.zip friend_2_complex/
# ... etc
```

### Option B — Share via Google Drive / Dropbox
Upload the folders and share links individually.

### Option C — They download from GitHub
Point them to: `github.com/AishwaryaBhanage/AI-DataLineage/tree/main/test_scenarios/friend_N_xxx`
They download manifest.json + run_results.json from there.

## The message to send each friend

```
Hey! I built an AI debugger for dbt data pipelines and need your honest feedback.

App URL: [YOUR DEPLOYED URL]
Your API key: [THEIR KEY FROM TABLE ABOVE]

Steps:
1. Open the app URL
2. Go to Settings → paste your API key → Save
3. Go to Debug → upload the 2 files I'm sending you → click Analyze
4. Follow the INSTRUCTIONS.md in your folder

I need feedback on:
- Did it work? Any errors?
- Was the diagnosis useful / understandable?
- Rate the experience 1-10
- What would you change?

Takes 5 minutes. Thank you!
```

## Collecting feedback

Create a simple Google Form or Notion page with these questions:
1. Which scenario were you testing? (1-5)
2. Did the analysis complete successfully? (Yes/No)
3. How many seconds did it take?
4. Was the root cause explanation clear? (1-10)
5. Was the corrected SQL correct? (Yes/No/Not sure)
6. Did the lineage graph render? (Yes/No)
7. Any errors or confusing UI elements?
8. Rate the overall experience (1-10)
9. What would you change?
10. Would you use this tool on a real project? (Yes/No/Maybe)
