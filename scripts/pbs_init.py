#!/usr/bin/env python3
"""Set up a second Proxmox Backup Server (PBS) that pulls a primary's backups, in one safe step.

  scripts/pbs.sh init [--host <host>]

init tags the host  util: [pbs]  (if not already) and stores a generated admin password as the encrypted secret
config/secrets/pbs/server.yml (read it with: scripts/secrets.sh view pbs.server). It runs the fleet preflight and shows what changed;
nothing is committed or pushed. The datastores, the remote (the primary PBS) and the pull job are plain fleet vars: see
config/vars/group/util_pbs.yml and runbooks/pbs.md. The secret of the primary's API token is added later with
  scripts/secrets.sh edit pbs.server    (key pbs_server_remote_secrets: {<remote name>: "<token secret>"})
"""
import json
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "pbs", "server.yml")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def tag_host(host):
    lines = open(HOSTS).read().split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^    {re.escape(host)}:\s*(#.*)?$", ln)), None)
    if start is None:
        die(f"host '{host}' is not in config/inventory/hosts.yml (register it first: scripts/node.sh add)")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^    \S", lines[i]) or re.match(r"^\S", lines[i])), len(lines))
    for i in range(start, end):
        m = re.match(r"^(      util:\s*\[)(.*?)(\].*)$", lines[i])
        if m:
            items = [x.strip() for x in m.group(2).split(",") if x.strip()]
            if "pbs" in items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(items + ['pbs'])}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return True
    lines.insert(start + 1, "      util: [pbs]")
    open(HOSTS, "w").write("\n".join(lines))
    return True


def sops_env():
    return dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))


def write_secret(data):
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write("---\n")
            for k, v in data.items():
                fh.write(f"{k}: {json.dumps(v)}\n")
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=sops_env(),
                           capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret: " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv):
    if not argv or argv[0] in ("-h", "--help") or argv[0] != "init":
        print(__doc__)
        return 0
    host = argv[argv.index("--host") + 1].lower() if "--host" in argv else None
    if not host:
        die("--host <name> is required: the host that will run it")
    if os.path.exists(SECRET):
        die("config/secrets/pbs/server.yml already exists; edit it with: scripts/secrets.sh edit pbs.server")
    print(f"Tagged {host} with util: [pbs]." if tag_host(host) else f"{host} already has util: [pbs].")
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_secret({"pbs_server_admin_password": secrets.token_urlsafe(18), "pbs_server_remote_secrets": {}})
    print("Wrote config/secrets/pbs/server.yml (encrypted, generated here; the admin password: scripts/secrets.sh view pbs.server).")
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nReview it, then:  git add -A && git commit -m 'pbs' && git push\n{host} starts PBS on its next run (or: scripts/reconcile-now.sh {host}).")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
