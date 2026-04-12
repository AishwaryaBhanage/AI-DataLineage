# Test Scenario 3 — Agentic (Deep Analysis) mode

**Your API key**: `dl_b0f56432cce1c27eaa126559`
**What you're testing**: The multi-agent ReAct mode where Claude autonomously decides what tools to call

## Steps

1. Open the app URL in your browser
2. Go to **Settings** → paste your API key above → Save
3. Go to **Debug** page
4. Switch to **"Deep analysis"** mode (right option — the one with the robot icon)
5. Upload the `manifest.json` and `run_results.json` from this folder
6. Click **"Start agent"**
7. **Wait 20-30 seconds** — this mode is slower because Claude is making multiple tool calls autonomously

## What you should see

1. First: a **"Agent is investigating"** card appears with a pulsing icon
2. The system polls every 2 seconds for status
3. When done: you should see:
   - **Agent Diagnosis** card with root cause in a gradient banner
   - **Agent reasoning trace** showing which tools Claude called (e.g. "Ingest artifacts → Inspect upstream SQL → Analyze error → ...")
   - **Validation checklist** with steps to verify the fix
   - **Corrected SQL** diff

## What's different from Scenario 1 (fast mode)

| Fast mode | Deep analysis (this one) |
|-----------|------------------------|
| 1 LLM call, ~4 seconds | 5-10 LLM calls, ~25 seconds |
| Pre-built evidence packet | Claude decides what to investigate |
| Cheaper (~$0.01) | More expensive (~$0.15) |
| Fixed analysis path | Adaptive — different tools per problem |

## Feedback I need from you

1. Did the "Agent is investigating" message appear immediately?
2. How long until the result appeared?
3. Which tools did Claude call? (Check the reasoning trace)
4. Was the diagnosis the same quality as fast mode, or better?
5. Was the wait time acceptable for the quality you got?
6. Rate the overall experience 1-10
