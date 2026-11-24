#!/usr/bin/env python3
"""Ask hosts to reconcile NOW instead of waiting for their 20-minute timer, and report how it went.

  scripts/reconcile-now.sh [hosts|all] [--check] [--no-wait] [--timeout SECONDS]

  hosts       comma-separated names from the host table, or all (default: all). Hosts that are offline are reported, not waited for.
  --check     report drift only: runs the reconciler in check mode on the host (changes nothing) and prints what WOULD change
  --no-wait   start the run and return at once (default: wait for each host to finish and print the outcome)
  --timeout   how long to wait for one host (default 900)

Systemd hosts: starts fleet-reconcile.service. Container-reconciled hosts (Unraid, or `reconciler: container` in the host table, e.g. Alpine): runs the reconciler container once.
Needs SSH to root@<tailscale ip>. By default it offers the fleet's admin key (the first baseline_admin_ssh_keys entry in config/vars/group/all.yml)
and lets your ssh agent (for example Bitwarden's) supply the private half, whatever ~/.ssh/config says. To use other options instead, set
RECONCILE_SSH_OPTS (falls back to AUDIT_SSH_OPTS), for example RECONCILE_SSH_OPTS="-o IdentitiesOnly=yes -i ~/.ssh/fleet_admin.pub"
A host that is already reconciling is not started twice: you just wait for the run that is going.
"""
import concurrent.futures
import json
import os
import re
import shlex
import subprocess
import sys
import time

import yaml

from hostkind import container_reconciled

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")


def hosts_table():
    data = yaml.safe_load(open(HOSTS)) or {}
    return {str(k).lower(): (v or {}) for k, v in (data.get("all", {}).get("hosts", {}) or {}).items()}


def tailnet():
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15)
        data = json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"ERROR: could not read the tailnet (tailscale status --json): {e}")
    peers = {}
    for p in list((data.get("Peer") or {}).values()) + [data.get("Self") or {}]:
        ips = [i for i in p.get("TailscaleIPs", []) if ":" not in i]
        peers[str(p.get("HostName", "")).lower()] = {"ip": ips[0] if ips else "", "online": p.get("Online")}
    return peers


def default_ssh_opts():
    """ssh options that pick the fleet's admin key without depending on ~/.ssh/config.

    Used when RECONCILE_SSH_OPTS / AUDIT_SSH_OPTS are not set. The first key in baseline_admin_ssh_keys (config/vars/group/all.yml) is written to a
    private temp file and offered with IdentitiesOnly, so an agent such as Bitwarden's supplies the matching private key even when your ssh config
    uses IdentitiesOnly with other identity files. Returns [] when no key is configured.
    """
    try:
        data = yaml.safe_load(open(os.path.join(ROOT, "config", "vars", "group", "all.yml"))) or {}
        key = next(k for k in (data.get("baseline_admin_ssh_keys") or []) if str(k).startswith("ssh-"))
    except Exception:  # noqa: BLE001
        return []
    import tempfile
    fd, path = tempfile.mkstemp(prefix="fleet-admin-", suffix=".pub")
    with os.fdopen(fd, "w") as fh:
        fh.write(str(key).strip() + "\n")
    import atexit
    atexit.register(lambda: os.path.exists(path) and os.remove(path))
    # One authenticated connection per host is reused by the next commands for a few minutes (ControlMaster), so an agent that asks for approval on every
    # signature (Bitwarden's) is asked once per host, not once per command. The socket directory is private to you.
    cm_dir = os.path.join(os.path.expanduser("~"), ".cache", "fleet-ssh")
    os.makedirs(cm_dir, mode=0o700, exist_ok=True)
    return ["-o", "IdentitiesOnly=yes", "-i", path, "-o", "ControlMaster=auto", "-o", f"ControlPath={cm_dir}/%C", "-o", "ControlPersist=5m"]


_SSH_OPTS = None
_PORTS = None


def ssh_port(ip):
    """The host's sshd port: its ssh_port in hosts.yml (default 22), looked up by tailnet address (for a host whose sshd is not on 22)."""
    global _PORTS
    if _PORTS is None:
        _PORTS = {}
        custom = {n: h["ssh_port"] for n, h in hosts_table().items() if h.get("ssh_port")}
        if custom:
            peers = tailnet()
            _PORTS = {peers[n]["ip"]: str(p) for n, p in custom.items() if n in peers and peers[n]["ip"]}
    return _PORTS.get(ip)


def ssh(ip, cmd, timeout=90):
    global _SSH_OPTS
    if _SSH_OPTS is None:
        env = os.environ.get("RECONCILE_SSH_OPTS") or os.environ.get("AUDIT_SSH_OPTS")
        _SSH_OPTS = shlex.split(env) if env else default_ssh_opts()
    opts = list(_SSH_OPTS)
    port = ssh_port(ip)
    if port:
        opts += ["-p", port]
    try:
        r = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
                            *opts, f"root@{ip}", cmd], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return 255, str(e)


RECAP = re.compile(r"ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)")


def summarize(text):
    """Last PLAY RECAP line in text -> 'ok=.. changed=.. failed=..' plus changed task names."""
    m = None
    for m in RECAP.finditer(text):
        pass
    recap = f"ok={m.group(1)} changed={m.group(2)} failed={m.group(4)}" if m else "no recap found"
    names, task = [], ""
    for ln in text.splitlines():
        if ln.startswith("TASK ["):
            task = re.sub(r"\][ *]*$", "", ln[6:])
        elif ln.startswith("changed: ") and task and task not in names:
            names.append(task)
    return recap, names


def one(name, host, peer, check, wait, timeout):
    if not peer or not peer["ip"]:
        return name, "not on the tailnet", ""
    if not peer["online"]:
        return name, "offline", ""
    ip = peer["ip"]
    if container_reconciled(host):
        mode = "check" if check else "apply"
        cmd = f"docker exec -e RECONCILE_MODE={mode} consigliere-reconcile consigliere-loop once 2>&1 | tail -400"
        if not wait:
            cmd = f"nohup sh -c 'docker exec -e RECONCILE_MODE={mode} consigliere-reconcile consigliere-loop once' >/dev/null 2>&1 & echo started"
        rc, out = ssh(ip, cmd, timeout=timeout)
        if not wait:
            return name, "started" if rc == 0 else f"could not start: {out[-80:]}", ""
        recap, names = summarize(out)
        return name, ("ok" if rc == 0 else f"FAILED (exit {rc})") + f"  {recap}", "; ".join(names[:6])
    if check:
        cmd = ("set -a; . /etc/fleet-reconcile.env; set +a; RECONCILE_MODE=check "
               "/opt/fleet-reconcile/framework/hosts/bootstrap/reconcile.sh 2>&1 | tail -600")
        rc, out = ssh(ip, cmd, timeout=timeout)
        recap, names = summarize(out)
        return name, ("check done" if rc == 0 else f"check FAILED (exit {rc})") + f"  {recap}", "would change: " + "; ".join(names[:6]) if names else ""
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    rc, out = ssh(ip, "touch /opt/fleet-reconcile/force-run; systemctl start --no-block fleet-reconcile && echo started")
    if rc != 0:
        return name, f"could not start: {out[-80:]}", ""
    if not wait:
        return name, "started", ""
    deadline = time.time() + timeout
    time.sleep(4)
    while time.time() < deadline:
        rc, out = ssh(ip, "systemctl is-active fleet-reconcile")
        if out.strip() not in ("active", "activating"):
            break
        time.sleep(8)
    else:
        return name, f"still running after {timeout}s", ""
    rc, out = ssh(ip, f"systemctl show fleet-reconcile -p Result --value; git -C /opt/fleet-reconcile/fleet-config log --oneline -1 | cut -c1-48; "
                      f"journalctl -u fleet-reconcile --since '{started}' --no-pager 2>/dev/null | sed 's/^[^]]*]: //' | tail -800", timeout=240)
    if rc == 255:
        return name, "finished, but its result could not be read (" + out[-70:] + ")", ""
    lines = out.splitlines()
    result, commit = (lines[0] if lines else "?"), (lines[1] if len(lines) > 1 else "")
    recap, names = summarize("\n".join(lines[2:]))
    return name, ("ok" if result == "success" else f"FAILED ({result})") + f"  {recap}  @ {commit}", "changed: " + "; ".join(names[:6]) if names else ""


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    check, wait = "--check" in argv, "--no-wait" not in argv
    timeout = int(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 900
    skip = {argv[argv.index("--timeout") + 1]} if "--timeout" in argv else set()
    words = [a for a in argv if not a.startswith("--") and a not in skip]
    table = hosts_table()
    wanted = list(table) if not words or words[0] == "all" else [h.strip().lower() for h in words[0].split(",")]
    unknown = [h for h in wanted if h not in table]
    if unknown:
        sys.exit(f"ERROR: not in the host table: {', '.join(unknown)}")
    peers = tailnet()
    print(f"{'Checking drift on' if check else 'Reconciling'} {len(wanted)} host(s): {', '.join(wanted)}\n")
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(one, n, table[n], peers.get(n), check, wait, timeout): n for n in wanted}
        for f in concurrent.futures.as_completed(futs):
            name, status, extra = f.result()
            results[name] = (status, extra)
            print(f"  {name:10} {status}" + (f"\n             {extra}" if extra else ""), flush=True)
    bad = [n for n, (s, _) in results.items() if "FAILED" in s or "could not" in s or "still running" in s]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
