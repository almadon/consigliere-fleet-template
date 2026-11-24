#!/usr/bin/env python3
"""Run things on hosts NOW: a command, package updates, or a careful reboot. Everything over SSH as root on the tailnet.

  scripts/fleet-run.sh HOSTS -- COMMAND...            run a command on each host (in parallel; output grouped per host)
  scripts/fleet-run.sh HOSTS --update                 apt update and upgrade (non-interactive), then say whether a reboot is needed
  scripts/fleet-run.sh HOSTS --reboot [--if-needed]   reboot ONE HOST AT A TIME, wait for each to come back and check it is healthy
  scripts/fleet-run.sh HOSTS --status                 uptime, reboot-required, failed units, running containers, last reconcile

  HOSTS     comma-separated names from the host table, or `all` (every host EXCEPT Unraid: those must be named on purpose)
  --yes     do not ask for confirmation (needed for scripts; `all` and --reboot ask otherwise)
  --serial  one host at a time for COMMAND/--update too (--reboot is always serial); --jobs N sets the parallel width (default 4)
  --if-needed       with --reboot: only hosts that have /var/run/reboot-required
  --keep-going      with --reboot/--serial: carry on with the next host after a failure (default: stop)
  --timeout S       how long to wait for one host (command/update: default 1800; reboot: how long it may stay away, default 600)
  --dry-run         say what would happen, touch nothing
  --address NAME=IP use this address for NAME instead of looking it up on the tailnet (repeatable; NAME need not be in the host table)

SSH uses the fleet's admin key like reconcile-now.sh (RECONCILE_SSH_OPTS overrides). Nothing here changes the fleet repo.
"""
import concurrent.futures
import os
import shlex
import subprocess
import sys
import threading
import time

import reconcile_now as R
from hostkind import container_reconciled

LOCK = threading.Lock()


def say(host, text):
    with LOCK:
        for ln in str(text).rstrip().splitlines() or [""]:
            print(f"[{host}] {ln}", flush=True)


def ssh(ip, cmd, timeout):
    return R.ssh(ip, cmd, timeout=timeout)


def run_command(name, ip, cmd, timeout):
    rc, out = ssh(ip, cmd, timeout)
    say(name, out)
    return rc == 0, f"exit {rc}"


UPDATE = ("export DEBIAN_FRONTEND=noninteractive; "
          "apt-get update -q 2>&1 | tail -2; "
          "apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade 2>&1 | tail -4; "
          "echo \"upgradable left: $(apt list --upgradable 2>/dev/null | grep -c upgradable)\"; "
          "[ -f /var/run/reboot-required ] && echo 'REBOOT REQUIRED: yes' || echo 'REBOOT REQUIRED: no'")

STATUS = ("echo \"up $(uptime -p | sed 's/^up //'), load $(cut -d' ' -f1-3 /proc/loadavg)\"; "
          "[ -f /var/run/reboot-required ] && echo 'reboot required: YES' || echo 'reboot required: no'; "
          "echo \"failed units: $(systemctl --failed --no-legend 2>/dev/null | wc -l)\"; "
          "command -v docker >/dev/null && echo \"containers running: $(docker ps -q | wc -l)\"; "
          "echo \"last reconcile: $(systemctl show fleet-reconcile -p Result --value 2>/dev/null) at $(systemctl show fleet-reconcile -p ExecMainExitTimestamp --value 2>/dev/null)\"")


def reboot_one(name, ip, timeout, if_needed):
    if if_needed:
        rc, out = ssh(ip, "[ -f /var/run/reboot-required ] && echo yes || echo no", 30)
        if out.strip() != "yes":
            say(name, "no reboot needed (skipped)")
            return True, "skipped"
    rc, boot_before = ssh(ip, "cat /proc/sys/kernel/random/boot_id", 30)
    if rc != 0:
        say(name, f"cannot reach the host: {boot_before[-80:]}")
        return False, "unreachable"
    say(name, "rebooting...")
    ssh(ip, "nohup sh -c 'sleep 2; systemctl reboot' >/dev/null 2>&1 & echo scheduled", 30)
    started = time.time()
    went_down = False
    deadline = started + timeout
    time.sleep(6)
    while time.time() < deadline:
        rc, out = ssh(ip, "cat /proc/sys/kernel/random/boot_id", 12)
        if rc != 0:
            went_down = True
        elif out.strip() != boot_before.strip():
            took = int(time.time() - started)
            rc, health = ssh(ip, "echo \"systemd: $(systemctl is-system-running 2>&1)\"; echo \"failed units: $(systemctl --failed --no-legend | wc -l)\"; "
                                 "command -v docker >/dev/null && echo \"containers: $(docker ps -q | wc -l) running\"", 60)
            say(name, f"back after {took}s ({'went down and came back' if went_down else 'new boot'})\n{health}")
            return True, f"back in {took}s"
        time.sleep(8)
    say(name, f"did NOT come back within {timeout}s")
    return False, "did not return"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    flags = {a for a in argv if a.startswith("--")}

    def val(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    addr = {}
    for i, a in enumerate(argv):
        if a == "--address" and i + 1 < len(argv) and "=" in argv[i + 1]:
            k, v = argv[i + 1].split("=", 1)
            addr[k.lower()] = v
    skip_vals = {val("--timeout"), val("--jobs")} | {argv[i + 1] for i, a in enumerate(argv) if a == "--address" and i + 1 < len(argv)}
    words = [a for a in argv if not a.startswith("--") and a not in skip_vals]
    if not words:
        sys.exit("ERROR: name the hosts (comma-separated) or `all`. See --help.")
    mode = "reboot" if "--reboot" in flags else "update" if "--update" in flags else "status" if "--status" in flags else "command" if cmd else None
    if mode is None:
        sys.exit("ERROR: give a command after `--`, or one of --update, --reboot, --status.")

    table = R.hosts_table()
    want = words[0]
    if want == "all":
        names = [n for n, h in table.items() if not container_reconciled(h)]
    else:
        names = [h.strip().lower() for h in want.split(",") if h.strip()]
    unknown = [n for n in names if n not in table and n not in addr]
    if unknown:
        sys.exit(f"ERROR: not in the host table (and no --address): {', '.join(unknown)}")
    peers = {} if all(n in addr for n in names) else R.tailnet()
    targets, problems = [], []
    for n in names:
        ip = addr.get(n) or (peers.get(n) or {}).get("ip")
        online = True if n in addr else bool((peers.get(n) or {}).get("online"))
        container = container_reconciled(table.get(n, {}))
        if not ip or not online:
            problems.append(f"{n}: offline or not on the tailnet")
        elif container and mode in ("update", "reboot"):
            problems.append(f"{n}: container-reconciled host (Unraid or Alpine: no apt here; update or reboot it from its own console)")
        else:
            targets.append((n, ip))
    timeout = int(val("--timeout", 600 if mode == "reboot" else 1800))
    jobs = int(val("--jobs", 4))
    serial = mode == "reboot" or "--serial" in flags

    desc = {"reboot": "REBOOT", "update": "apt update + upgrade on", "status": "status of", "command": "run `" + " ".join(cmd) + "` on"}[mode]
    print(f"Plan: {desc} {len(targets)} host(s): {', '.join(n for n, _ in targets) or '-'}" + (" (one at a time)" if serial else f" ({jobs} in parallel)"))
    for p in problems:
        print(f"  skipped: {p}")
    if "--dry-run" in flags or not targets:
        print("(dry run: nothing done)" if "--dry-run" in flags else "Nothing to do.")
        return 0 if "--dry-run" in flags else 1
    if mode in ("reboot", "update", "command") and "--yes" not in flags and (want == "all" or mode == "reboot" or len(targets) > 1):
        if not sys.stdin.isatty() or input("Go ahead? [y/N] ").strip().lower() != "y":
            print("Not confirmed: add --yes to run without asking.")
            return 1

    if mode == "command":
        remote = " ".join(shlex.quote(c) for c in cmd) if len(cmd) > 1 else cmd[0]
        job = lambda n, ip: run_command(n, ip, remote, timeout)  # noqa: E731
    elif mode == "update":
        job = lambda n, ip: run_command(n, ip, UPDATE, timeout)  # noqa: E731
    elif mode == "status":
        job = lambda n, ip: run_command(n, ip, STATUS, 120)  # noqa: E731
    else:
        job = lambda n, ip: reboot_one(n, ip, timeout, "--if-needed" in flags)  # noqa: E731

    results = {}
    if serial:
        for n, ip in targets:
            ok, note = job(n, ip)
            results[n] = (ok, note)
            if not ok and "--keep-going" not in flags:
                print(f"Stopping after the failure on {n} (use --keep-going to continue).")
                break
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = {pool.submit(job, n, ip): n for n, ip in targets}
            for f in concurrent.futures.as_completed(futs):
                results[futs[f]] = f.result()
    print("\nSummary:")
    for n, _ in targets:
        if n in results:
            print(f"  {n:10} {'ok' if results[n][0] else 'FAILED'}  {results[n][1]}")
        else:
            print(f"  {n:10} not run")
    return 0 if all(ok for ok, _ in results.values()) and len(results) == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
