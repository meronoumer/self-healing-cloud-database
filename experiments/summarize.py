"""Turn one trial's raw logs into a row in experiments/results.csv.

Automated trial: reads the fault-to-detection and start-request timestamps
from experiments/manager.jsonl, restricted to mode=="real" entries only --
simulation output must never contribute to a results row.

Manual trial: there is no manager running, so the human-issued start time
is passed on the command line and recorded as manual_delay_s, a column
that only ever appears for manual rows. Automated rows get
detection_interval_s instead. The two are never collapsed into one column,
so a reader can't mistake a human's reaction time for the manager's.
"""

import argparse
import csv
import json
from pathlib import Path

RESULTS_PATH = Path("experiments/results.csv")
FIELDS = [
    "run_id", "kind", "stop_time", "start_request_time",
    "manual_delay_s", "detection_interval_s",
    "last_pre_failure_commit_time", "first_post_failure_commit_time",
    "client_visible_write_gap_s", "acknowledged_writes_missing", "notes",
]


def load_jsonl(path):
    records = []
    if not Path(path).exists():
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def first_after(records, stop_time, event, mode):
    for r in records:
        if r.get("event") == event and r.get("mode") == mode and r.get("t", -1) >= stop_time:
            return r
    return None


def ack_times(records, run_id):
    return sorted(r["t"] for r in records if r.get("run_id") == run_id and "ack_time" in r)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--kind", choices=["manual", "automated"], required=True)
    p.add_argument("--stop-time", type=float, required=True,
                    help="epoch seconds captured immediately before the destroy command, "
                         "e.g. python3 -c \"import time;print(time.time())\"")
    p.add_argument("--start-time", type=float,
                    help="manual only: epoch seconds when you issued `virsh start` by hand")
    p.add_argument("--manager-log", default="experiments/manager.jsonl")
    p.add_argument("--ack-log", default="experiments/acknowledged.jsonl")
    p.add_argument("--missing-count", type=int, required=True,
                    help="paste the count printed by workload/verify.py for this run")
    p.add_argument("--notes", default="")
    args = p.parse_args()

    acks = load_jsonl(args.ack_log)
    ack_ts = ack_times(acks, args.run_id)
    pre = [t for t in ack_ts if t < args.stop_time]
    post = [t for t in ack_ts if t >= args.stop_time]
    last_pre = pre[-1] if pre else None
    first_post = post[0] if post else None
    gap = (first_post - last_pre) if (last_pre is not None and first_post is not None) else None

    row = {
        "run_id": args.run_id,
        "kind": args.kind,
        "stop_time": args.stop_time,
        "last_pre_failure_commit_time": last_pre,
        "first_post_failure_commit_time": first_post,
        "client_visible_write_gap_s": gap,
        "acknowledged_writes_missing": args.missing_count,
        "notes": args.notes,
    }

    if args.kind == "automated":
        mgr = load_jsonl(args.manager_log)
        declared = first_after(mgr, args.stop_time, "failure_declared", mode="real")
        requested = first_after(mgr, args.stop_time, "restart_requested", mode="real")
        row["start_request_time"] = requested["t"] if requested else None
        row["detection_interval_s"] = (declared["t"] - args.stop_time) if declared else None
        row["manual_delay_s"] = ""
        if not declared or not requested:
            row["notes"] = (row["notes"] + " manager log missing an expected real-mode event").strip()
    else:
        if args.start_time is None:
            p.error("--start-time is required for a manual run")
        row["start_request_time"] = args.start_time
        row["manual_delay_s"] = args.start_time - args.stop_time
        row["detection_interval_s"] = ""

    is_new = not RESULTS_PATH.exists()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)

    for k in FIELDS:
        print(f"{k}: {row.get(k)}")


if __name__ == "__main__":
    main()
