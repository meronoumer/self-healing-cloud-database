"""Compare host-side acknowledged writes against what PostgreSQL actually has.

Run after a trial, once the writer has been stopped and the database is
reachable again.
"""

import json
import os
import sys

import psycopg

run_id = sys.argv[1]
ack_path = sys.argv[2] if len(sys.argv) > 2 else "experiments/acknowledged.jsonl"

acknowledged = set()
with open(ack_path, encoding="utf-8") as ack_file:
    for line in ack_file:
        event = json.loads(line)
        if event["run_id"] == run_id:
            acknowledged.add(event["seq"])

with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as conn:
    rows = conn.execute(
        "SELECT seq FROM writes WHERE run_id = %s", (run_id,)
    ).fetchall()
present = {row[0] for row in rows}
missing = sorted(acknowledged - present)

print(f"run: {run_id}")
print(f"acknowledged: {len(acknowledged)}")
print(f"present after recovery: {len(acknowledged) - len(missing)}")
print(f"missing acknowledged IDs: {missing}")
