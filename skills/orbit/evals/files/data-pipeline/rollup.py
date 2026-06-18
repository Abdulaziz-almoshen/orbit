"""Run-by-hand ETL: extract events -> roll up -> overwrite prod table + email. No checks."""
import os
import requests

ANALYTICS_API_KEY = os.environ.get("ANALYTICS_API_KEY", "")
WAREHOUSE_DSN = os.environ.get("WAREHOUSE_DSN", "")
SMTP_URL = os.environ.get("SMTP_URL", "")


def extract(day: str):
    r = requests.get(
        "https://api.example-analytics.com/v1/events",
        headers={"Authorization": f"Bearer {ANALYTICS_API_KEY}"},
        params={"day": day},
    )
    return r.json()["events"]


def transform(events):
    rollup = {}
    for e in events:  # no validation; NULLs and dupes pass straight through
        rollup[e["metric"]] = rollup.get(e["metric"], 0) + e["value"]
    return rollup


def load_to_prod(day: str, rollup: dict):
    """Overwrites the production daily_metrics table. No dry-run, no backup."""
    import psycopg2
    conn = psycopg2.connect(WAREHOUSE_DSN)
    cur = conn.cursor()
    cur.execute("DELETE FROM daily_metrics WHERE day = %s", (day,))
    for metric, value in rollup.items():
        cur.execute(
            "INSERT INTO daily_metrics (day, metric, value) VALUES (%s, %s, %s)",
            (day, metric, value),
        )
    conn.commit()


def email_leadership(day: str, rollup: dict):
    requests.post(SMTP_URL, json={"to": "leadership@example.com",
                                  "subject": f"Daily metrics {day}", "body": str(rollup)})


if __name__ == "__main__":
    day = "2024-03-01"
    r = transform(extract(day))
    load_to_prod(day, r)        # straight to prod
    email_leadership(day, r)    # auto-send
