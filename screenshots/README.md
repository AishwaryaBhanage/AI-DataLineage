# Screenshots

This folder holds screenshots referenced in the main `README.md`. When you
take new screenshots, save them with these **exact filenames** so the image
links resolve correctly on GitHub:

| Filename | What it shows |
|----------|--------------|
| `01_debug_page.png` | The main Debug page with mode + source selectors (empty state, before running any analysis) |
| `02_analyze_result.png` | Fast mode analysis result — the hero shot showing root cause card, stat row, confidence |
| `03_lineage_graph.png` | Zoomed-in lineage DAG with the broken model highlighted in red |
| `04_agentic_result.png` | Agentic (deep) analysis result with the agent reasoning trace + tool timeline |
| `05_file_upload.png` | Drag-and-drop file upload zone in action |
| `06_dbt_cloud_source.png` | dbt Cloud URL input field with the "Detected" auto-extract chip visible |
| `07_jobs_history.png` | Jobs page showing multiple past runs with status badges |
| `08_usage_stats.png` | Usage page with the stat cards and request breakdown |

## How to take them

1. Start the app — either local dev (`localhost:5173`) or Docker container (`localhost:9000`) or your deployed AWS URL
2. Set up your API key in the Settings page
3. Run the sample analysis (Load sample failure or use bundled `dbt_demo`)
4. Navigate to each page and use your browser's screenshot tool
5. Crop cleanly — include only the main content area, not your browser chrome
6. Save at retina resolution if possible (2x on Mac)
7. Drop the files in this folder with the filenames above

## Tips for a good screenshot

- **Use 100% zoom** so text is crisp
- **Light background** — your app uses a light theme, keep it clean
- **Descriptive state** — for result screenshots, pick a case where the LLM
  produced a clear diagnosis (e.g. `customer_lifetime_metrics` with all 6
  errors, so the hypothesis list looks impressive)
- **Window width** — ~1400-1600px wide gives a balanced look on GitHub
