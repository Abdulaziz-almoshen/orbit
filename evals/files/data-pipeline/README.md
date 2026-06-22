# MetricsRollup (WIP)

Internal ETL job: pulls events from our analytics API, rolls them up into daily metrics,
and writes them to the production warehouse. One script we run by hand each morning.

## Current pieces
- `rollup.py` — extract → transform → load. Overwrites the prod `daily_metrics` table and
  emails the summary to the leadership list.

## Known issues / TODO
- No memory between runs; we re-explain the column mapping every time we tweak the prompt.
- No validation — a bad extract once wrote NULLs over a good day of data.
- It overwrites the prod table directly, no dry-run, no backup. Scary.
- It auto-emails leadership even when the numbers look obviously wrong.
- No structure: extract, transform, validate, load all jammed in one function.
- No limits — a retry bug once re-ran the load 20 times.
- Env: `ANALYTICS_API_KEY`, `WAREHOUSE_DSN`, `SMTP_URL`.
