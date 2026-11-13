# Runbook: `pg-recovery-test` failure/recovery trials

Everything below runs on the Dell (Ubuntu host, libvirt, `qemu:///system`),
not on any other machine. It assumes the VM exists, boots, and PostgreSQL
is installed and running *inside* the guest (already verified via
`sudo -u postgres psql` on the console, per `build_guide.md` Step C). What
hasn't been confirmed yet is a write from the **host**, over the libvirt
network — that's Step 0 below, and it's a hard prerequisite: do not start
Procedure A until Step 0's exit check passes.

---

## Step 0 — Dependencies and host-to-guest connection

### 0.1 Host-side dependencies

```bash
sudo apt install python3-venv postgresql-client
cd self-healing-cloud-database
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "psycopg[binary]"
```

### 0.2 Configure the host-to-guest PostgreSQL connection

This is `build_guide.md` Step D, not yet done from the host. Find the
guest's IP and confirm the guest side is reachable:

```bash
virsh -c qemu:///system domifaddr pg-recovery-test
```

Inside the guest (console session, `sudo -u postgres psql`), if not
already created:

```sql
CREATE ROLE lab LOGIN PASSWORD 'choose-a-local-test-password';
CREATE DATABASE failure_lab OWNER lab;
```

Find and edit the guest's `postgresql.conf` (`listen_addresses = '*'`)
and `pg_hba.conf` (add a line restricting access to the libvirt NAT
subnet only — check the actual subnet with `sudo virsh net-dumpxml
default` on the host), then inside the guest:

```bash
sudo systemctl restart postgresql
```

### 0.3 Set the connection environment and prove it from the host

```bash
export DATABASE_URL='host=VM_IP port=5432 dbname=failure_lab user=lab password=...'
export VM_NAME=pg-recovery-test
psql "$DATABASE_URL" -c "SELECT 1;"
```

Replace `VM_IP` with the address from `domifaddr`. This is the first
command that actually talks to PostgreSQL from the Dell host rather than
from inside the guest console — if this fails, don't move on; the
problem is in `listen_addresses`, `pg_hba.conf`, or the libvirt subnet,
not in anything below.

### 0.4 Create the table and verify a write from the host

```bash
psql "$DATABASE_URL" -c "CREATE TABLE writes (run_id text NOT NULL, seq bigint NOT NULL, PRIMARY KEY (run_id, seq));"
python workload/write_client.py smoke-00
```

Let it print a handful of `acknowledged smoke-00:N` lines, then Ctrl+C.

```bash
python workload/verify.py smoke-00
```

**Exit check:** `verify.py` prints `missing acknowledged IDs: []`. This
is the first confirmed write from the Dell host, over the libvirt
network, through this project's own client — distinct from the earlier
guest-console check, and the thing you said you still needed. Only once
this passes should you move on to Procedure A.

There are two procedures below. **Procedure A is the timed manual
baseline — run this next.** Procedure B is the same experiment with the
manager active, run afterward once A has given you a working, repeatable
measurement.

---

## Procedure A — Timed manual baseline (manager off)

Three terminals. The manager process is never started in this procedure
— you play its role by hand, and your own reaction time becomes part of
the measurement (`manual_delay_s`, computed in A5 below).

### A1. Start the writer (terminal 1)

```bash
python workload/write_client.py manual-01
```

Pick a run ID you haven't used before. Let it print `acknowledged
manual-01:N` for at least 15 seconds before touching anything else, so
there's an unambiguous last good commit before the fault.

### A2. Capture the stop time and force-stop the VM (terminal 2)

```bash
python3 -c "import time; print(time.time())"   # <- write this number down: --stop-time
virsh -c qemu:///system destroy pg-recovery-test
```

This is the host's `time.time()` clock — the same clock
`workload/write_client.py` uses for every `ack_time` it logs. `destroy`
leaves the virtual disk in place; nothing is deleted.

### A3. Wait, then capture the start time and start the VM (terminal 2)

Watch terminal 1: you'll see `connect failed; retrying ...` lines while
the guest is down. Decide how long to wait (or just restart immediately
— that choice is part of what you're measuring), then:

```bash
python3 -c "import time; print(time.time())"   # <- write this number down: --start-time
virsh -c qemu:///system start pg-recovery-test
```

### A4. Confirm the writer resumes (terminal 1)

Keep watching terminal 1. The first `acknowledged manual-01:N` line
printed after A2 is the first successful commit after recovery. Let it
print a few more, then stop the writer with Ctrl+C.

### A5. Verify and summarize (terminal 2 or 3)

```bash
python workload/verify.py manual-01
```

Note the "missing acknowledged IDs" count, then:

```bash
python experiments/summarize.py \
  --run-id manual-01 --kind manual \
  --stop-time <number from A2> \
  --start-time <number from A3> \
  --missing-count <number verify.py printed>
```

This appends one row to `experiments/results.csv`. Because `--kind
manual` was passed, the script never reads `experiments/manager.jsonl`
at all — there's no manager log to read, since nothing was polling. It
fills `manual_delay_s = start_time - stop_time` and leaves
`detection_interval_s` blank, so your reaction time is never confused
with an automated detection interval later.

**How "first commit on either side of the outage" is picked:** every
line in `experiments/acknowledged.jsonl` for this run ID has a
confirmed-commit timestamp (`ack_time`). `summarize.py` splits those
into everything before `--stop-time` and everything at-or-after it, and
reports the last of the first group and the first of the second — i.e.
the very last commit you saw before you killed the VM, and the very
first one after it came back. The gap between those two is
`client_visible_write_gap_s`.

---

## Procedure B — Automated trial (manager on)

Four terminals. Same writer and same fault; the difference is a manager
process now sits between the fault and the restart.

### B0. Pre-flight: verify the probe and VM query while healthy

Before touching the fault:

```bash
python recovery/manager.py --mode real --verify-only
```

Expected: one line in `experiments/manager.jsonl` with `"event":
"verify_probe", "db_responds": true, "vm_state": "running"`, and the
printed message says the manager would report HEALTHY **and would not
issue a start request**. `verify_once()` in `recovery/manager.py` never
calls `vm_start()` on this path — there is no code path by which this
step can touch the VM. Run it two or three times to confirm it's stable.

### B1. Start the manager (terminal 1)

```bash
python recovery/manager.py --mode real
```

Leave it running. It polls every second, requires 3 consecutive failed
probes before declaring failure, and issues at most one `virsh start`
per failure episode (`--max-restarts 1`, the core-experiment setting).

### B2. Start the writer (terminal 2)

```bash
python workload/write_client.py auto-01
```

Same as A1 — a fresh run ID, at least 15 seconds of commits before the
fault.

### B3. Capture the stop time and stop the VM (terminal 3)

```bash
python3 -c "import time; print(time.time())"   # <- --stop-time
virsh -c qemu:///system destroy pg-recovery-test
```

### B4. Watch the manager detect and recover (terminal 1 / `experiments/manager.jsonl`)

Expected sequence, every line tagged `"mode": "real"`:

```
probe_failed (consecutive_failures=1)
probe_failed (consecutive_failures=2)
probe_failed (consecutive_failures=3)
failure_declared (vm_state="shut off")
restart_requested (vm_state="shut off")
... (manager keeps probing once a second)
service_recovered
```

`failure_declared` is the manager's fault-to-detection timestamp.
`restart_requested` is the single `virsh start` it issued. If you
instead see `vm_running_but_database_unreachable`, libvirt is reporting
the guest as up while PostgreSQL still isn't answering — the manager
will not restart the VM again in that state; see the diagnostic section
below.

### B5. Confirm the writer resumes (terminal 2 / `experiments/writer_events.jsonl`)

Same as A4: the first `acknowledged auto-01:N` line after the stop is
the first successful post-failure commit. Stop the writer with Ctrl+C.

### B6. Verify and summarize

```bash
python workload/verify.py auto-01
python experiments/summarize.py \
  --run-id auto-01 --kind automated \
  --stop-time <number from B3> \
  --missing-count <number verify.py printed>
```

With `--kind automated`, `summarize.py` reads `restart_requested` and
`failure_declared` out of `experiments/manager.jsonl` (filtered to
`mode == "real"`) to fill `start_request_time` and
`detection_interval_s`. `manual_delay_s` is left blank — there is no
human reaction time to record in this procedure.

### Diagnosing "the VM came back but the writer still can't commit"

Three layers can each fail independently. Read them in this order using
the actual logs, not assumptions:

1. **Guest boot** — `vm_state` in `experiments/manager.jsonl`. Once it
   flips from `"shut off"` to `"running"`, the guest OS is up. This says
   nothing about PostgreSQL.
2. **Database probe success** — look for `service_recovered` in
   `experiments/manager.jsonl`. This means `SELECT 1` succeeded: the
   PostgreSQL process is accepting connections and answering a trivial,
   read-only query. It does **not** mean a real write will succeed —
   `SELECT 1` doesn't touch the `writes` table, take a lock, or write
   WAL.
3. **Workload failure** — look at `experiments/writer_events.jsonl` in
   the same window. It records four distinct outcomes per attempt, not
   just acknowledged/failed:
   - `connect_failed` — couldn't open a connection at all. Definite:
     nothing was ever sent. Retries the same `(run_id, seq)`.
   - `insert_failed` — connected, but the INSERT itself raised before
     COMMIT was ever sent. Not durable; definitely did not happen.
     Retries the same `(run_id, seq)`.
   - `uncertain` — INSERT was sent, COMMIT was sent, and the connection
     broke before the COMMIT reply arrived. The write may have landed
     server-side; the client cannot tell. Kept out of
     `acknowledged.jsonl`, and this `seq` is **abandoned, not retried**
     — the next attempt gets a fresh `(run_id, seq)`. If the COMMIT
     actually landed despite the lost reply, it leaves a row in
     `writes` under an ID that was never logged as acknowledged; that's
     harmless, since `verify.py` only ever checks IDs that were
     actually logged as acknowledged.
   - `acknowledged` — confirmed commit.

   `connect_failed` entries appearing *after* `service_recovered` would
   be a real contradiction worth flagging (manager says the DB is up,
   writer can't even connect). `insert_failed` or repeated `uncertain`
   entries after `service_recovered`, by contrast, mean the TCP/auth
   path `SELECT 1` exercises is fine, but something past that point
   isn't — lock contention during crash recovery, a replica that came
   up read-only, disk full, etc. That's a workload-level failure riding
   on top of a healthy probe, not an outage.

Correlate by the `t` field (present in both files, same `time.time()`
clock) rather than eyeballing order — `manager.jsonl` and
`writer_events.jsonl` are two independent processes writing to two
independent files.

## Repeating trials

Reuse terminals; pick a new run ID each time. The manager can stay
running continuously across many Procedure B trials — `manager.jsonl`
just accumulates more entries, bounded per trial by your `--stop-time`
values. Record the actual number of trials you complete, including any
that failed for tooling reasons (e.g. forgot to bump the run ID) — note
why, don't just delete the row.

## Simulation stays out of the results — by construction, not by filtering

`recovery/manager.py --mode sim` exercises the state-machine logic with
no VM and no `psycopg` dependency at all, using a scripted sequence of
probe outcomes, e.g.:

```bash
python recovery/manager.py --mode sim --sim-script \
  '[[true,"running"],[false,"shut off"],[false,"shut off"],[false,"shut off"],[true,"running"]]'
```

Sim mode writes to `experiments/manager_sim.jsonl`, a different file
from real mode's `experiments/manager.jsonl` — there is no shared file
to accidentally forget to filter. `experiments/summarize.py` only ever
reads `experiments/manager.jsonl` by default, so a sim run cannot leak
into `results.csv` even if you mistype a flag.

## How to report a trial

Report what was actually observed: one acknowledged row (or, after
Procedure A/B, a run ID's worth of acknowledged rows) found present
after restart, plus the measured gap and detection interval where
applicable. `fsync` and `synchronous_commit` have not been recorded for
these trials, and no server log or WAL state has been inspected. Don't
describe a result as confirming what PostgreSQL flushed or replayed —
that would be a claim about internal durability mechanics this
experiment hasn't gathered evidence for. The experiment establishes
whether the client-visible outcome (row present, write gap, missing
acknowledged count) holds up across trials; it doesn't establish why at
the storage-engine level unless the durability settings and WAL/server
logs are captured as a separate, explicit step.
