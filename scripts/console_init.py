#!/usr/bin/env python3
"""Set up the fleet console (Muximux) in one safe step, and leave it for you to review and push.

The console signs in through Pocket ID, so first create (in Pocket ID) a confidential OIDC client:
  callback URL   https://cz.ctrl.example.com/api/auth/oidc/callback   (muximux_url + /api/auth/oidc/callback)
  allowed group  Muximux-Admins   (and send the groups claim)
Then run:   scripts/console.sh init [--host <host>]

It tags the host  util: [muximux]  (if it is not already), writes the secret config/secrets/muximux/server.yml
(client id + client secret, encrypted for that host), runs the fleet preflight and shows the diff. Nothing is
committed or pushed. For scripts: MUXIMUX_CLIENT_ID and MUXIMUX_CLIENT_SECRET replace the prompts.
"""
import getpass
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
VARS = os.path.join(ROOT, "config", "vars", "group", "util_muximux.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "muximux", "server.yml")


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
            if "muximux" in items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(items + ['muximux'])}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return True
    lines.insert(start + 1, "      util: [muximux]")
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
        die("config/vars/group/util_muximux.yml is missing (it holds the console URL, tiles and route)")
    if os.path.exists(SECRET):
        die("config/secrets/muximux/server.yml already exists (rotate it with: scripts/secrets.sh edit muximux.server)")

    cid = os.environ.get("MUXIMUX_CLIENT_ID") or input("Pocket ID client id: ").strip()
    secret = os.environ.get("MUXIMUX_CLIENT_SECRET") or getpass.getpass("Pocket ID client secret (hidden): ").strip()
    if len(cid) < 8 or len(secret) < 8:
        die("the client id or secret looks too short")

    if tag_host(host):
        print(f"Tagged {host} with util: [muximux].")
    else:
        print(f"{host} already has util: [muximux].")
    # the encryption rule exists only once a host carries the tag, so sync first
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(f'---\nmuximux_oidc_client_id: "{cid}"\nmuximux_oidc_client_secret: "{secret}"\n')
        env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret: " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("Wrote config/secrets/muximux/server.yml (encrypted).")

    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print("\nReview it, then:  git add -A && git commit -m 'fleet console' && git push")
    print(f"{host} starts the console on its next run (within ~20 minutes).")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
