"""Recovery manager for the pg-recovery-test VM experiment.

Two probe backends, selected with --mode:
  real  psycopg against DATABASE_URL, `virsh` against qemu:///system
  sim   a scripted fake, for exercising the state machine with no VM at all

Real and sim modes log to different files (manager.jsonl vs.
manager_sim.jsonl) so simulation output can never land in the same file
the summarizer reads for experimental results -- there's no filter to
remember, they're just different paths.
"""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_PATHS = {
    "real": Path("experiments/manager.jsonl"),
    "sim": Path("experiments/manager_sim.jsonl"),
}


class RealProbe:
    """Only this class touches psycopg/virsh. sim mode never imports either,
    so the state machine can be exercised on a box with no DB driver and
    no libvirt installed at all -- exactly the Mac-side check this is for.
    """

    def __init__(self, dsn, vm_name):
        self.dsn = dsn
        self.vm_name = vm_name

    def database_responds(self):
        import psycopg
        try:
            with psycopg.connect(self.dsn, connect_timeout=1) as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    def vm_state(self):
        result = subprocess.run(
            ["virsh", "-c", "qemu:///system", "domstate", self.vm_name],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip().lower()

    def vm_start(self):
        return subprocess.run(
            ["virsh", "-c", "qemu:///system", "start", self.vm_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )


class SimScriptExhausted(Exception):
    """Raised when a scripted sim run has no more steps to play back."""


class SimProbe:
    """Scripted fake so the state machine can be exercised with no VM.

    `script` is a list of (db_ok, vm_state) steps, each consumed by one
    call to database_responds(). vm_state() reports the state paired with
    the most recently consumed step (the two are polled together on a
    real probe too). Once the script runs out, the next probe call raises
    SimScriptExhausted instead of looping or inventing more data -- a
    demo run should end exactly when its script says it should.
    vm_start() only increments a counter; it never touches real hardware.
    """

    def __init__(self, script):
        if not script:
            raise ValueError("sim script must have at least one step")
        self.script = script
        self.i = 0
        self.last_state = None
        self.starts_issued = 0

    def database_responds(self):
        if self.i >= len(self.script):
            raise SimScriptExhausted()
        ok, state = self.script[self.i]
        self.i += 1
        self.last_state = state
        return ok

    def vm_state(self):
        return self.last_state

    def vm_start(self):
        self.starts_issued += 1
        return None


def log(mode, event, **fields):
    now = time.time()
    record = {
        "t": now,
        "iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "mode": mode,
        "event": event,
        **fields,
    }
    path = LOG_PATHS[mode]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)


def verify_once(probe, mode):
    """One probe + one VM-state query. Never calls vm_start()."""
    healthy = probe.database_responds()
    state = probe.vm_state()
    log(mode, "verify_probe", db_responds=healthy, vm_state=state)
    if healthy:
        print("Result: database responds; manager would report HEALTHY "
              "and would NOT issue a start request.")
    else:
        print("Result: database probe failed; a running manager would "
              "begin counting consecutive failures.")


def run(probe, mode, poll_interval, fail_threshold, recovery_timeout, max_restarts):
    failures = 0
    restarts_issued = 0
    while True:
        if probe.database_responds():
            if failures:
                log(mode, "database_healthy_again", consecutive_failures_cleared=failures)
            failures = 0
            restarts_issued = 0
            time.sleep(poll_interval)
            continue

        failures += 1
        log(mode, "probe_failed", consecutive_failures=failures)
        if failures < fail_threshold:
            time.sleep(poll_interval)
            continue

        state = probe.vm_state()
        log(mode, "failure_declared", consecutive_failures=failures, vm_state=state)

        if state in {"shut off", "crashed"}:
            if restarts_issued >= max_restarts:
                log(mode, "restart_limit_reached", restarts_issued=restarts_issued)
                time.sleep(poll_interval)
                continue
            log(mode, "restart_requested", vm_state=state)
            probe.vm_start()
            restarts_issued += 1

            deadline = time.monotonic() + recovery_timeout
            recovered = False
            while time.monotonic() < deadline:
                if probe.database_responds():
                    log(mode, "service_recovered")
                    recovered = True
                    break
                time.sleep(poll_interval)
            if not recovered:
                log(mode, "recovery_timeout")
            failures = 0
        else:
            log(mode, "vm_running_but_database_unreachable", vm_state=state)
            failures = 0

        time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["real", "sim"], default="real")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run one probe and one VM-state query, log the result, and exit. "
             "Never issues a start request.",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--fail-threshold", type=int, default=3)
    parser.add_argument("--recovery-timeout", type=float, default=120)
    parser.add_argument("--max-restarts", type=int, default=1,
                         help="Start requests allowed per failure episode (one, for the core experiment).")
    parser.add_argument(
        "--sim-script",
        help='sim mode only: JSON list of [db_ok, vm_state] steps, e.g. '
             '\'[[true,"running"],[false,"shut off"],[false,"shut off"],'
             '[false,"shut off"],[true,"running"]]\'. One step is consumed '
             "per probe call; the run ends when the script runs out.",
    )
    args = parser.parse_args()

    if args.mode == "real":
        dsn = os.environ["DATABASE_URL"]
        vm_name = os.environ.get("VM_NAME", "pg-recovery-test")
        probe = RealProbe(dsn, vm_name)
    else:
        if not args.sim_script:
            parser.error("--mode sim requires --sim-script")
        steps = [tuple(step) for step in json.loads(args.sim_script)]
        probe = SimProbe(steps)

    if args.verify_only:
        verify_once(probe, args.mode)
        return

    try:
        run(
            probe,
            args.mode,
            poll_interval=args.poll_interval,
            fail_threshold=args.fail_threshold,
            recovery_timeout=args.recovery_timeout,
            max_restarts=args.max_restarts,
        )
    except SimScriptExhausted:
        starts = getattr(probe, "starts_issued", None)
        log(args.mode, "sim_script_exhausted", starts_issued=starts)


if __name__ == "__main__":
    main()
