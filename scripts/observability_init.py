#!/usr/bin/env python3
"""Set up Loki (logs) and Grafana (dashboards) on a host in one safe step, and leave it for you to review and push.

  scripts/observability.sh init [--host <host>]

Before running it, in Pocket ID create a confidential OIDC client for Grafana:
  callback URL  https://gf.ctrl.example.com/login/generic_oauth   (grafana_server_url + /login/generic_oauth)
  groups claim  allowed; groups Grafana-Admins (Admin) and Grafana-Editors (Editor) decide the role, others are Viewers
Then this: asks for the client id and secret (hidden), generates a break-glass admin password, stores all three encrypted as
config/secrets/grafana/server.yml, tags the host  util: [loki, grafana] , runs the fleet preflight and shows what changed.
Nothing is committed or pushed. For scripts: GRAFANA_CLIENT_ID and GRAFANA_CLIENT_SECRET replace the prompts.
Loki needs no secret. If the host has data_disk_device set (vars/host/<host>.yml) the blank disk is formatted on the next run.
"""
import getpass
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "grafana", "server.yml")
WANT = ["loki", "grafana"]


def die(msg):
    sys.exit(f"ERROR: {msg}")


def tag_host(host):
    """Add the util tags in WANT that the host lacks; returns the ones added."""
    lines = open(HOSTS).read().split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^    {re.escape(host)}:\s*(#.*)?$", ln)), None)
    if start is None:
        die(f"host '{host}' is not in config/inventory/hosts.yml (register it first: scripts/node.sh add)")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^    \S", lines[i]) or re.match(r"^\S", lines[i])), len(lines))
    for i in range(start, end):
        m = re.match(r"^(      util:\s*\[)(.*?)(\].*)$", lines[i])
        if m:
            items = [x.strip() for x in m.group(2).split(",") if x.strip()]
            added = [w for w in WANT if w not in items]
            if added:
                lines[i] = f"{m.group(1)}{', '.join(items + added)}{m.group(3)}"
                open(HOSTS, "w").write("\n".join(lines))
            return added
    lines.insert(start + 1, f"      util: [{', '.join(WANT)}]")
    open(HOSTS, "w").write("\n".join(lines))
    return list(WANT)


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    host = argv[argv.index("--host") + 1].lower() if "--host" in argv else None
    if not host:
        die("--host <name> is required: the host that will run it")
    for f in ("util_loki.yml", "util_grafana.yml"):
        if not os.path.exists(os.path.join(ROOT, "config", "vars", "group", f)):
            die(f"config/vars/group/{f} is missing")
    if os.path.exists(SECRET):
        added = tag_host(host)
        print(f"The secret grafana.server already exists; tagged {host} with: {', '.join(added) or 'nothing new'}.")
    else:
        cid = os.environ.get("GRAFANA_CLIENT_ID") or input("Pocket ID client id for Grafana: ").strip()
        csec = os.environ.get("GRAFANA_CLIENT_SECRET") or getpass.getpass("Pocket ID client secret (hidden): ").strip()
        if len(cid) < 8 or len(csec) < 8:
            die("the client id or secret looks too short")
        added = tag_host(host)
        print(f"Tagged {host} with util: {', '.join(added) or '(already there)'}.")
        # the encryption rule exists only once a host carries the tag, so sync first
        subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.makedirs(os.path.dirname(SECRET), exist_ok=True)
        tmp = SECRET + ".new"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write("---\n"
                         f'grafana_server_oidc_client_id: "{cid}"\n'
                         f'grafana_server_oidc_client_secret: "{csec}"\n'
                         f'grafana_server_admin_password: "{secrets.token_urlsafe(24)}"\n')
            env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
            r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env,
                               capture_output=True, text=True)
            if r.returncode != 0:
                die("could not encrypt the secret: " + r.stderr.strip()[:200])
            os.replace(tmp, SECRET)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        print("Wrote config/secrets/grafana/server.yml (encrypted; the admin password was generated here: scripts/secrets.sh view grafana.server).")

    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nReview it, then:  git add -A && git commit -m 'loki and grafana' && git push\n"
          f"{host} starts Loki and Grafana on its next run (within ~20 minutes).")
    dd = os.path.join(ROOT, "config", "vars", "host", f"{host}.yml")
    if os.path.exists(dd) and re.search(r"^data_disk_device:\s*\S", open(dd).read(), re.M):
        print("NOTE: that run also formats the data disk named in vars/host/%s.yml if it is blank (a disk with a filesystem is never touched)." % host)
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
