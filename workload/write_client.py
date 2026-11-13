"""Continuous workload client for the pg-recovery-test experiment.

Writes one row per transaction. INSERT and COMMIT are two separate
network round trips, and a failure in each means something different,
so they get separate try/except blocks, separate outcomes, and different
retry behavior:

  connect_failed   psycopg could not open a connection at all -- nothing
                    was ever sent. Definite: this write did not happen.
                    Retries the SAME seq as a clean do-over.
  insert_failed     connected, but the INSERT itself raised before COMMIT
                    was ever sent. No COMMIT means Postgres guarantees
                    the transaction is not durable -- also definite.
                    Retries the SAME seq.
  uncertain          the INSERT was sent and accepted, COMMIT was sent,
                    and the connection broke before the COMMIT reply
                    came back. The write may have committed server-side;
                    the client cannot tell from here. Because the
                    outcome is unknown rather than definite, this seq is
                    abandoned -- the NEXT attempt gets a fresh
                    (run_id, seq), so no future attempt is ever retried
                    under an ID whose fate is unresolved.

Only a confirmed commit is appended to acknowledged.jsonl (read by
verify.py). uncertain is deliberately kept OUT of acknowledged.jsonl. If
an uncertain COMMIT actually landed server-side despite the lost reply,
it leaves a row in `writes` under an ID that was never logged as
acknowledged -- harmless, since verify.py only ever checks IDs that
were actually logged as acknowledged. All outcomes are appended to
writer_events.jsonl for diagnosing a recovery window.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

dsn = os.environ["DATABASE_URL"]
run_id = sys.argv[1] if len(sys.argv) > 1 else "run-01"

ack_path = Path("experiments/acknowledged.jsonl")
events_path = Path("experiments/writer_events.jsonl")
ack_path.parent.mkdir(parents=True, exist_ok=True)


def _safe_close(conn):
    try:
        conn.close()
    except psycopg.Error:
        pass


def write_event(path, **fields):
    now = time.time()
    record = {
        "run_id": run_id,
        "t": now,
        "iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        **fields,
    }
    with path.open("a", encoding="utf-8", buffering=1) as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return record


seq = 1
while True:
    try:
        conn = psycopg.connect(dsn, connect_timeout=2)
    except psycopg.Error as exc:
        write_event(events_path, seq=seq, outcome="connect_failed", error=str(exc))
        print(f"connect failed; retrying {run_id}:{seq}: {exc}", flush=True)
        time.sleep(0.5)
        continue

    try:
        conn.execute(
            "INSERT INTO writes (run_id, seq) VALUES (%s, %s) "
            "ON CONFLICT (run_id, seq) DO NOTHING",
            (run_id, seq),
        )
    except psycopg.Error as exc:
        # Failed before COMMIT was ever sent: not durable, full stop.
        write_event(events_path, seq=seq, outcome="insert_failed", error=str(exc))
        print(f"connected but insert failed; retrying {run_id}:{seq}: {exc}", flush=True)
        _safe_close(conn)
        time.sleep(0.5)
        continue

    try:
        conn.commit()
    except psycopg.Error as exc:
        # COMMIT was sent; we lost the connection before seeing the reply.
        # The write may or may not have landed -- do not count it either
        # way, and do not retry this ID. Advance past it so the next
        # attempt is an unambiguous fresh write.
        write_event(events_path, seq=seq, outcome="uncertain", error=str(exc))
        print(f"commit reply lost; abandoning {run_id}:{seq}, advancing", flush=True)
        _safe_close(conn)
        seq += 1
        time.sleep(0.5)
        continue

    _safe_close(conn)
    record = write_event(events_path, seq=seq, outcome="acknowledged")
    write_event(ack_path, seq=seq, ack_time=record["t"])
    print(f"acknowledged {run_id}:{seq}", flush=True)
    seq += 1
    time.sleep(0.1)  # 10 writes per second
