
Self-Healing Cloud Database: Step-by-Step Build Guide
Project: Self-Healing Cloud Database
Course: CSC 262 Operating Systems
Working deadline: Present results during the week of December 7; submit final code, results, and report by December 22 at 3 p.m.
The project in plain language
You will run PostgreSQL—a real database program—inside a virtual machine (VM). A second program, the recovery manager, will run on your Ubuntu laptop outside the VM. It will check whether PostgreSQL is responding. If the VM stops, the manager will notice and try to start it again. A small client program will keep sending writes to PostgreSQL and save a local record of which writes received a successful confirmation.
You will deliberately stop the test VM, let the recovery manager bring it back, and measure how long the database was unavailable and whether the writes it had confirmed are still present.

The core project is the recovery manager plus a repeatable failure experiment. PostgreSQL supplies database behavior; you are not implementing a database engine. Restarting the same VM is the first recovery strategy. Starting a replacement VM is an extension because you must decide how the replacement gets the database files.

What runs where
Ubuntu laptop (host)
├── Recovery manager (Python)
├── Workload client and local acknowledged-write log (Python)
├── Experiment runner and CSV results
└── QEMU/KVM + libvirt
    └── Ubuntu Server VM (guest)
        └── PostgreSQL
The host runs the manager and client so they keep running when the guest VM stops. The manager checks PostgreSQL with a small SQL query. For the first automated failure case, it can start a VM that libvirt reports as stopped. The client writes to PostgreSQL over the local virtual network.
Recommended first-version technology stack
Part	Choice	Why
Host	Your existing Dell laptop running Ubuntu	You already use this machine for xv6/QEMU work.
Virtualization	QEMU/KVM managed by libvirt; virsh for VM status/start/stop	QEMU/KVM runs the VM; libvirt gives the manager a controllable VM interface. Confirm KVM/libvirt availability before committing to it.
Guest	Ubuntu Server VM	A small, disposable Linux environment for the database.
Database	PostgreSQL with its default durability settings for the first experiment	Gives you a real database without having to implement one. Record settings; do not tune them during the initial experiment.
Recovery manager	Python 3, using a PostgreSQL driver (psycopg) and Python's subprocess/standard library	Easier to develop and inspect than a low-level manager; its job is control and measurement, not high-speed request serving.
Workload and verifier	Python 3 + psycopg	Sends numbered writes, records acknowledgements locally, and checks results after recovery.
Results	CSV, then a simple Python plot or table	Easy to inspect, repeat, and include in the report.
Do not install a cloud service or pay for cloud VMs for the core experiment. First get a controlled local VM experiment working. The final report should describe this as a single-host virtualized testbed, not as a test of failures across independent cloud machines.
Laptop capacity check
Run these commands on the Ubuntu host and save the output in your notes:
uname -r
nproc
free -h
df -h
ls -l /dev/kvm
They report the kernel version, CPU count, memory, free disk space, and whether the KVM device is available. Aim for at least 20 GB of free disk space for the OS image, VM disk, and experiment files. A single VM is the initial target; do not plan on two simultaneously running VMs until you know how much RAM is available. If /dev/kvm is missing, first check BIOS virtualization support and the Ubuntu KVM/libvirt setup; do not jump to replication or replacement-VM work.
The experiment you will run
Research question
When PostgreSQL runs inside a VM, how quickly can a recovery manager restore service after a VM failure, and do writes acknowledged before the failure survive recovery?
First failure to test
The core failure is an abrupt stop of the PostgreSQL VM. This tests recovery after the guest OS and its PostgreSQL process stop at once. It does not test a physical cloud-host failure, a network partition, or simultaneous failures.
Once the VM-stop experiment works, you may add a PostgreSQL-process crash as a second case. Keep it separate: the VM remains alive in that case, so the manager needs a way to restart PostgreSQL inside the guest. Treat that as a later milestone, not a prerequisite for the first working result.

Workload and correctness check
The client will repeatedly insert rows with a unique run ID and sequence number, for example (run_03, 17). Use one transaction per row and a modest fixed rate, such as ten writes per second. After PostgreSQL confirms a commit, the client appends that ID and timestamp to a log file on the host. The host and its log are outside the guest VM, so the VM failure does not erase the record of what the client saw.
After recovery, the verifier queries PostgreSQL and compares its rows with the host-side acknowledgement log. A row that the client logged as acknowledged but cannot find is a missing acknowledged write. A request that timed out before the client received a confirmation is uncertain, not a confirmed success; count it separately if it helps explain the results.

Use disposable test data only. Keep PostgreSQL's durability settings unchanged for the core experiment, and record the configuration so the result has a clear boundary. PostgreSQL uses write-ahead logging to recover database state after a crash, so successful recovery and survival of acknowledged writes are testable outcomes, not assumptions. genui{"citation":{"ref":"turn14search0"}}

Metrics and timestamps
The fault-injection script records t0 immediately before it stops the VM. The recovery manager records t1 when it decides the VM is unavailable. The client records t2 when it receives its first successful database response after recovery.
Detection time: t1 - t0.
Manager recovery time: t2 - t1.
Client-observed downtime: time from the last successful request before failure to the first successful request after recovery. This reflects the interruption the client experiences.
Missing acknowledged writes: count of host-logged confirmed IDs absent from PostgreSQL after recovery.
Make one practice run to find bugs in the test itself. Then aim for ten successful runs of the core VM-failure setup if time permits. Report the actual run count and the median and range; do not discard inconvenient runs without explaining why.
Build sequence, with deliverables and exit checks
Step 0 — Organize and check the host (Nov 6)
Make a project folder or Git repository with notes/, workload/, recovery/, experiments/, and report/.
Save the laptop capacity-check output above in notes/environment.md.
In notes/plan.md, copy the research question, architecture, first failure, and four metrics from this guide.
Finish the first project journal/log due Nov 6: what you decided, what remains unknown, and the next experiment you plan to build.
Deliverable: first journal submitted; environment and scope recorded.
Exit check: you know whether one local VM is plausible on your laptop.
Step 1 — Explain the design for the progress presentation (by your presentation during the week of Nov 9)
Prepare a simple diagram of the host and guest VM. Explain what the manager watches, what failure you will cause, how you will recover, and what you will measure. Be explicit that the replacement VM is an extension, not part of the first implementation.
Deliverable: 10-minute progress presentation with architecture, experiment plan, and current setup status.
Exit check: someone can understand what runs on the laptop versus inside the VM.

Step 2 — Create the VM and verify PostgreSQL manually (Nov 10–13)
Install/configure QEMU/KVM and libvirt on Ubuntu if the capacity check supports them.
Create one Ubuntu Server VM with a persistent virtual disk.
Install PostgreSQL inside the VM.
Confirm the host can connect to PostgreSQL over the local VM network. Restrict access to the local test network; do not expose the database to the public internet.
Create a test database/table and manually insert, query, stop, and restart PostgreSQL.
Deliverable: setup instructions in README.md and a repeatable manual database check.
Exit check: PostgreSQL starts and the host can insert and read a test row.
Step 3 — Build the workload client and verifier (Nov 14–16)
Write a Python client that inserts one uniquely numbered row per transaction at a fixed rate.
After each successful commit response, append the run ID, sequence ID, and timestamp to a host-side acknowledgement log.
Handle connection failures by retrying the connection. Use unique IDs so retries do not create duplicate logical writes.
Write a verifier that loads the acknowledgement log, queries PostgreSQL after recovery, and lists missing acknowledged IDs.
Deliverable: workload script, acknowledgement log, and verifier.
Exit check: with no failure, every acknowledged ID is found by the verifier.
Step 4 — Run manual failure tests (Nov 17–19)
Run the workload for a short period.
Force-stop the disposable VM from the host; record the injection time.
Restart the VM manually and wait until the client succeeds again.
Save the client log and check which acknowledged rows survived.
Repeat once to confirm your procedure gives usable results.
Use libvirt's force-stop operation only on this disposable guest. It terminates the guest abruptly, so PostgreSQL must recover from the state on its virtual disk when it boots again. genui{"citation":{"ref":"turn14search9"}}
Deliverable: two manual-run records with timestamps and verification output.
Exit check: you can distinguish failure, downtime, and missing acknowledged data from the logs.

Step 5 — Implement the recovery manager (Nov 20–26)
Implement a simple state machine: HEALTHY → SUSPECT → RECOVERING → HEALTHY.
Every second, try a small database health query such as SELECT 1.
Require three consecutive failed checks before declaring the database unavailable. This avoids acting on one transient failed check.
For the first version, handle the VM-stopped case: confirm libvirt says the VM is stopped, start it, and keep checking until PostgreSQL responds.
Log every state change and timestamp to a file.
Run the workload during an automated recovery and use the verifier afterward.
Deliverable: recovery/manager.py plus one end-to-end automated run.
Exit check: after you trigger the VM failure, the manager starts it without manual intervention and the client resumes successfully.
Step 6 — Repeat, measure, and decide on the extension (Nov 27–Dec 2)
Run the core experiment repeatedly and save one CSV row per run.
Calculate detection time, manager recovery time, client downtime, and missing acknowledged writes.
Make a small table or graph showing the results and their spread.
Only if the core is reliable, investigate the second failure type or replacement-VM recovery.
Deliverable: results CSV, summary graph/table, and a short limitations note. The second journal/log is due Nov 20; include implementation progress and early outcomes there, then keep the later results for your presentation and report.
Exit check: the core results are repeatable and you can explain what the experiment does and does not establish.
Step 7 — Present and finish (week of Dec 7 through Dec 22)
Present the working core and measurements during the week of Dec 7.
After the presentation, use remaining time for the replacement extension only if the core is already complete; otherwise improve the analysis, code instructions, and report.
Write the final report with the question, architecture, failure model, method, results, limitations, and what you learned about OS processes, virtualization, persistent storage, and recovery.
Rerun the core experiment from the README instructions and check that the output matches the report.
Deliverable: final presentation, report, code, and results due Dec 22 at 3 p.m.
Exit check: another student can follow the setup and reproduce at least the core test.
What to postpone
Do not build PostgreSQL itself. Do not begin with a standby replica, network partition, split-brain testing, a large matrix of storage settings, or dozens of trials across many configurations. These add separate engineering questions. The core result is a working failure/recovery loop with a trustworthy workload log and a repeatable measurement. The replacement VM is the first extension, and it must have an explicit data-transfer plan before you implement it.
Known limitations to report
All guest VMs run on one physical laptop, so they share its CPU, memory, storage, and physical network interface. The experiment measures recovery in this local virtualized setup; it does not establish performance across separate cloud hosts or availability zones. The single host is also a point of failure for the recovery manager itself. State these limits plainly rather than trying to simulate a whole cloud provider.
Hands-on setup: exact first commands
Do these in order. Stop at the first step that fails and record the error; do not stack more setup changes on top of an unknown failure.
A. Check resources
On the Ubuntu host:
uname -r
nproc
free -h
df -h /
ls -l /dev/kvm
Save the complete output. If /dev/kvm exists, continue to B. If it does not, check that hardware virtualization is enabled in the laptop firmware and ask for help with the KVM setup before creating the VM. For one Ubuntu Server guest, start with 2 virtual CPUs, 2 GB RAM, and a 20 GB virtual disk. If the host has limited memory or disk, lower the VM allocation or stop and reassess before downloading an ISO.
B. Install and check VM management
On the Ubuntu host:
sudo apt update
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients virt-manager
Ubuntu documents QEMU/KVM with libvirt as its VM setup and provides virt-manager as a graphical manager. genui{"citation":{"ref":"turn15search1"}}
Check that libvirt can answer:

virsh -c qemu:///system list --all
If it reports that the daemon is unavailable, start it and retry:
sudo systemctl enable --now libvirtd
virsh -c qemu:///system list --all
Check the default virtual network:
sudo virsh net-list --all
If a network named default exists but is inactive, start it and make it start automatically:
sudo virsh net-start default
sudo virsh net-autostart default
If virsh only works with sudo, stop here and fix your libvirt permissions before writing the recovery manager. On a standard Ubuntu system, add your login to the libvirt and KVM groups, then log out and back in:
sudo adduser "$(id -un)" libvirt
sudo adduser "$(id -un)" kvm
Retry virsh -c qemu:///system list --all. The manager needs permission to query and start the VM without an interactive password prompt.
C. Create one disposable Ubuntu Server VM
Download an Ubuntu Server LTS installer ISO from Ubuntu's official download page.
Open Virtual Machine Manager (virt-manager).
Choose Create a new virtual machine and select Local install media (ISO image).
Select the ISO you downloaded. Choose Linux/Ubuntu if prompted.
Allocate 2 CPUs, 2 GB memory, and a 20 GB disk as a starting point, subject to the host resource check.
Name the VM pg-lab and use the default libvirt NAT network. Do not configure bridged/public networking.
Complete the Ubuntu Server installation. Create a normal user and record the VM username/password somewhere private.
In the VM, install PostgreSQL and the QEMU guest agent:
sudo apt update
sudo apt install postgresql qemu-guest-agent
sudo systemctl enable --now postgresql qemu-guest-agent
In the VM, check its IP address and PostgreSQL status:
ip -4 addr
sudo systemctl status postgresql --no-pager
On the host, check that libvirt sees the VM and its IP:
virsh -c qemu:///system domstate pg-lab
virsh -c qemu:///system domifaddr pg-lab
Write down the VM IP. If domifaddr has no address yet, confirm the guest agent is running and use ip -4 addr in the VM console.
Deliverable: notes/environment.md contains host output, VM name, guest IP, allocated RAM/CPUs/disk, and the PostgreSQL status. Exit check: virsh domstate pg-lab reports running, and PostgreSQL is active in the guest.

Before proceeding, reboot the VM normally once and check that it gets the same IP address. The manager and workload use that IP. If it changes, configure a DHCP reservation in libvirt before collecting experiment results.

D. Create a test database and allow only the lab VM network
Inside the VM, enter PostgreSQL's administrative shell:
sudo -u postgres psql
At the psql prompt, create a lab account and database (replace the sample password with a unique local test password):
CREATE ROLE lab LOGIN PASSWORD 'choose-a-local-test-password';
CREATE DATABASE failure_lab OWNER lab;
\q
Find the PostgreSQL configuration-file paths from inside the VM:
sudo -u postgres psql -tAc 'SHOW config_file;'
sudo -u postgres psql -tAc 'SHOW hba_file;'
Edit the postgresql.conf file printed by the first command. Set listen_addresses = '*' for this isolated lab VM. This makes PostgreSQL listen on its interfaces; access is still restricted by pg_hba.conf and the private VM network. In the pg_hba.conf file printed by the second command, add a rule for only the libvirt NAT subnet, replacing the sample subnet if your default network uses a different one:
host    failure_lab    lab    192.168.122.0/24    scram-sha-256
You can inspect the actual subnet on the host with:
sudo virsh net-dumpxml default
Restart PostgreSQL in the VM:
sudo systemctl restart postgresql
From the host, install the PostgreSQL command-line client if needed, then connect (replace VM_IP with the guest IP):
sudo apt install postgresql-client
psql "host=VM_IP port=5432 dbname=failure_lab user=lab" -W
Enter the test password when prompted. Remote PostgreSQL access depends on both listen_addresses and the host-based access rules; do not use a trust rule or expose port 5432 to a public network. genui{"citation":{"ref":"turn15search21"}}
Deliverable: a host-side successful psql connection and a screenshot or copied terminal output in your notes. Exit check: you can connect from the host, run SELECT 1;, and exit with \q.

Starter workload and verifier
Once the host can connect, set up the Python side on the host. In the project folder:
sudo apt install python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "psycopg[binary]"
Put the connection string in a local environment variable, not in the source file or Git:
export DATABASE_URL='host=VM_IP port=5432 dbname=failure_lab user=lab password=YOUR_TEST_PASSWORD'
Replace VM_IP and YOUR_TEST_PASSWORD with your values. Create the table once from the host:
psql "$DATABASE_URL" -c "CREATE TABLE writes (run_id text NOT NULL, seq bigint NOT NULL, PRIMARY KEY (run_id, seq));"
The client code below is the continuous loop. For the first smoke test, start it, wait until you see one acknowledged message, then stop it with Ctrl+C and run the verifier. Once that passes, use a fresh run ID and leave the client running during the failure experiment. For each row, the code commits first; only after the commit call returns successfully does it append the run_id, sequence ID, and timestamp to experiments/acknowledged.jsonl on the host. Keep that output outside the guest VM. If the connection fails during a request, the client retries the same ID; the table's primary key prevents duplicate logical rows. A commit may have succeeded even if its response did not reach the client, so only count writes the client actually observed as acknowledged, and describe timed-out requests as uncertain.
Create workload/verify.py to read the host acknowledgement log, query writes for those IDs after recovery, and print (1) acknowledged count, (2) found count, and (3) the missing acknowledged IDs. Do not proceed to automated recovery until this verifier reports zero missing IDs in normal no-failure runs.

Recovery manager: exact behavior before code details
The manager is a host-side Python loop. It should do these steps in order:
Attempt a short-timeout PostgreSQL connection and execute SELECT 1.
If that works, record HEALTHY, clear the failure counter, wait one second, and check again.
If it fails, increment a consecutive-failure counter. Do nothing until three checks have failed.
At three failures, record SUSPECT and run virsh -c qemu:///system domstate pg-lab.
For the core VM-stop test, if libvirt says the domain is stopped, record RECOVERING and run virsh -c qemu:///system start pg-lab.
Keep probing PostgreSQL once a second. When SELECT 1 succeeds, record HEALTHY and the recovery timestamp.
If the VM is still running while PostgreSQL fails, log DB_UNREACHABLE_VM_RUNNING and do not loop-start the VM. Recovering a crashed PostgreSQL process inside a live guest requires a separate command path (for example, SSH or the QEMU guest agent); add it only after VM-stop recovery works.
The one-second interval and three-check threshold are initial experimental settings, not universal best values. Record them in the report. Do not add a timeout sweep until the end. Libvirt's force-stop operation terminates the guest abruptly; virsh start starts a defined stopped guest. genui{"citation":{"refs":["turn15search0","turn14search9"]}}
Manager log fields: timestamp, state, probe result, libvirt VM state, action, and action result. Store one JSON object per line in experiments/manager.jsonl.

Minimal workload client code
Save this as workload/write_client.py. It uses one row ID repeatedly until PostgreSQL confirms the commit, then advances to the next ID. This makes retries safe if a commit response is lost during the outage.
import json
import os
import sys
import time
from pathlib import Path

import psycopg

dsn = os.environ["DATABASE_URL"]
run_id = sys.argv[1] if len(sys.argv) > 1 else "run-01"
ack_path = Path("experiments/acknowledged.jsonl")
ack_path.parent.mkdir(parents=True, exist_ok=True)
seq = 1

with ack_path.open("a", encoding="utf-8", buffering=1) as ack_file:
    while True:
        try:
            # Leaving the connection context commits the transaction.
            # We log an acknowledgement only after that commit returns.
            with psycopg.connect(dsn, connect_timeout=2) as conn:
                conn.execute(
                    "INSERT INTO writes (run_id, seq) VALUES (%s, %s) "
                    "ON CONFLICT (run_id, seq) DO NOTHING",
                    (run_id, seq),
                )

            event = {
                "run_id": run_id,
                "seq": seq,
                "ack_time": time.time(),
            }
            ack_file.write(json.dumps(event) + "\n")
            ack_file.flush()
            os.fsync(ack_file.fileno())
            print(f"acknowledged {run_id}:{seq}", flush=True)
            seq += 1
            time.sleep(0.1)  # 10 writes per second
        except psycopg.Error as exc:
            print(f"database unavailable; retrying {run_id}:{seq}: {exc}", flush=True)
            time.sleep(0.5)
Run it from the project root after exporting DATABASE_URL:
source .venv/bin/activate
python workload/write_client.py run-01
Stop it with Ctrl+C after recovery. The client keeps retrying through the outage; because the sequence number does not advance until a commit succeeds, a retry refers to the same logical write.
Minimal verifier code
Save as workload/verify.py:
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
Run it after the workload has stopped and PostgreSQL is back:
python workload/verify.py run-01
Minimal recovery manager code
Save as recovery/manager.py. This first version automatically handles only a VM that libvirt reports as stopped. It intentionally logs, rather than trying to repair, the different case where the VM is running but PostgreSQL is not answering.
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

dsn = os.environ["DATABASE_URL"]
vm_name = os.environ.get("VM_NAME", "pg-lab")
log_path = Path("experiments/manager.jsonl")
log_path.parent.mkdir(parents=True, exist_ok=True)


def log(event, **fields):
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with log_path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
        out.flush()


def database_responds():
    try:
        with psycopg.connect(dsn, connect_timeout=1) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def vm_state():
    result = subprocess.run(
        ["virsh", "-c", "qemu:///system", "domstate", vm_name],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return result.stdout.strip().lower()


def virsh(*args):
    return subprocess.run(
        ["virsh", "-c", "qemu:///system", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


failures = 0
while True:
    if database_responds():
        if failures:
            log("database_healthy_again")
        failures = 0
        time.sleep(1)
        continue

    failures += 1
    log("probe_failed", consecutive_failures=failures)
    if failures < 3:
        time.sleep(1)
        continue

    try:
        state = vm_state()
        log("failure_suspected", vm_state=state)
        if state in {"shut off", "crashed"}:
            log("restart_requested", vm=vm_name)
            result = virsh("start", vm_name)
            log("vm_start_command_returned", output=result.stdout.strip())

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if database_responds():
                    log("service_recovered", vm=vm_name)
                    failures = 0
                    break
                time.sleep(1)
            else:
                log("recovery_timeout", vm=vm_name)
                failures = 0
        else:
            log("vm_running_but_database_unreachable", vm_state=state)
            failures = 0
    except (subprocess.SubprocessError, OSError) as exc:
        log("recovery_manager_error", error=str(exc))
        failures = 0

    time.sleep(1)
Run it in a terminal on the host:
source .venv/bin/activate
export VM_NAME=pg-lab
python recovery/manager.py
Before adding a fault, verify it logs successful probes and can run virsh domstate pg-lab without sudo. Then start the workload in a second terminal and use a third terminal to force-stop the disposable VM. In a manual practice run, keep the manager stopped and restart the VM by hand; in the automated run, leave the manager running and let it issue virsh start.
Important: this is starter code for the core controlled experiment, not a production service. Add validation, configuration files, graceful shutdown, and more robust error handling after it works. Do not run the force-stop test against any VM that contains data you care about.

How to run one complete core trial
Confirm the VM is running and the host can connect to PostgreSQL.
Clear or create a new run-specific acknowledgement log. Use a unique run ID.
Start the recovery manager in terminal 1.
Start the workload client in terminal 2; let it write for at least 15 seconds.
In terminal 3, run date --iso-8601=ns and then virsh -c qemu:///system destroy pg-lab. This force-stops the disposable VM; it does not delete its virtual disk. Expect the client to see failed requests while the VM is off.
Watch the manager log. It should detect the outage and issue the VM start command. Wait until the client is successfully writing again.
Stop the workload cleanly with Ctrl+C. Run the verifier and save all three logs under the run ID.
Add one summary row to experiments/results.csv with run_id, failure type, injection timestamp, detection time, first-success timestamp, downtime, acknowledged count, missing-acknowledged count, and notes.
Do one practice trial first. Inspect all timestamps and verifier output before repeating. Then collect about ten valid core trials if run time permits. Do not silently remove a failed run; note whether it was a setup failure, tool failure, or a valid system outcome.
Replacement VM: gate before attempting
Do not make the replacement VM part of the core. A PostgreSQL guest's root disk contains the database files, so a blank replacement will not have the records. Reusing the old VM's disk is possible only after the old VM is confirmed stopped, and the same virtual disk must never be mounted read/write by two running VMs at once. Before coding this extension, first draw and write down: which VM owns the disk before failure, how the old VM is fenced/stopped, how the replacement attaches the disk, and how the client finds the database afterward. If any of those are unclear, document replacement as future work and finish the core measurement/report.
