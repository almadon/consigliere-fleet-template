#!/usr/bin/env python3
"""Set up cmdr (the fleet's control page) in one safe step, and leave it for you to review and push.

cmdr signs in through Pocket ID, so first create (in Pocket ID) a confidential OIDC client:
  callback URL   https://cmdr.ctrl.example.com/auth/callback   (cmdr_url + /auth/callback)
  scopes         openid, profile, email, groups  (send the groups claim)
  allowed group  admins.sysops   (cmdr_admin_groups in config/vars/group/util_cmdr.yml)
Then run:   scripts/cmdr.sh init [--host <host>]

It tags the host  util: [cmdr]  (if it is not already), writes the secret config/secrets/cmdr/server.yml (the client id and secret you give, and a
generated session secret, encrypted for that host), runs the fleet preflight and shows the diff. Nothing is committed or pushed. For scripts:
CMDR_CLIENT_ID and CMDR_CLIENT_SECRET replace the prompts.
"""
import getpass
import json
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
VARS = os.path.join(ROOT, "config", "vars", "group", "util_cmdr.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "cmdr", "server.yml")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def tag_host(host):
    lines = open(HOSTS).read().split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^    {re.escape(host)}:\s*(#.*)?$", ln)), None)
    if start is None:
        die(f"host '{host}' is not in config/inventory/hosts.yml")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^    \S", lines[i]) or re.match(r"^\S", lines[i])), len(lines))
    for i in range(start, end):
        m = re.match(r"^(      util:\s*\[)(.*?)(\].*)$", lines[i])
        if m:
            items = [x.strip() for x in m.group(2).split(",") if x.strip()]
            if "cmdr" in items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(items + ['cmdr'])}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return True
    lines.insert(start + 1, "      util: [cmdr]")
    open(HOSTS, "w").write("\n".join(lines))
    return True


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    host = argv[argv.index("--host") + 1].lower() if "--host" in argv else None
    if not host:
        die("--host <name> is required: the host that will run it")
    if not os.path.exists(VARS):
        die("config/vars/group/util_cmdr.yml is missing (it holds the URL, the tools and the host links)")
    if os.path.exists(SECRET):
        die("config/secrets/cmdr/server.yml already exists (rotate it with: scripts/secrets.sh edit cmdr.server)")
    cid = os.environ.get("CMDR_CLIENT_ID") or input("Pocket ID client id: ").strip()
    csecret = os.environ.get("CMDR_CLIENT_SECRET") or getpass.getpass("Pocket ID client secret (hidden): ").strip()
    if len(cid) < 8 or len(csecret) < 8:
        die("the client id or secret looks too short")
    print(f"Tagged {host} with util: [cmdr]." if tag_host(host) else f"{host} already has util: [cmdr].")
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write("---\n")
            for k, v in (("cmdr_oidc_client_id", cid), ("cmdr_oidc_client_secret", csecret), ("cmdr_session_secret", secrets.token_urlsafe(48))):
                fh.write(f"{k}: {json.dumps(v)}\n")
        env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret: " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("Wrote config/secrets/cmdr/server.yml (encrypted; the session secret was generated here).")
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nReview it, then:  git add -A && git commit -m 'cmdr' && git push\nThen: scripts/reconcile-now.sh {host}")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
