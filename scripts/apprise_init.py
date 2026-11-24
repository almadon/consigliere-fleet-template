#!/usr/bin/env python3
"""Set up the notification service (Apprise API) in one safe step, and leave it for you to review and push.

Run:   scripts/apprise.sh init [--host <host>]

It asks for the admin password for the admin panel (hidden; 12+ characters; leave empty to generate one that is written to a file only you can read, see below),
generates the panel's session secret, tags the host  util: [notify]  (if it is not already), writes the secret config/secrets/apprise/server.yml (encrypted for that
host), runs the fleet preflight and shows the diff. Nothing is committed or pushed. For scripts: APPRISE_ADMIN_PASSWORD replaces the prompt.
A generated password is saved to ~/.apprise-admin-password (mode 600): put it in your password manager, then delete the file.
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
VARS = os.path.join(ROOT, "config", "vars", "group", "util_notify.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "apprise", "server.yml")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def tag_host(host):
    """Add util: notify to the host. Also drops duplicate entries in that list (an earlier version of this script repeated another tag)."""
    lines = open(HOSTS).read().split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^    {re.escape(host)}:\s*(#.*)?$", ln)), None)
    if start is None:
        die(f"host '{host}' is not in config/inventory/hosts.yml")
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^    \S", lines[i]) or re.match(r"^\S", lines[i])), len(lines))
    for i in range(start, end):
        m = re.match(r"^(      util:\s*\[)(.*?)(\].*)$", lines[i])
        if m:
            items = [x.strip() for x in m.group(2).split(",") if x.strip()]
            unique = list(dict.fromkeys(items))
            added = "notify" not in unique
            if added:
                unique.append("notify")
            if unique == items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(unique)}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return added
    lines.insert(start + 1, "      util: [notify]")
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
        die("config/vars/group/util_notify.yml is missing")
    if os.path.exists(SECRET):
        die("config/secrets/apprise/server.yml already exists (rotate it with: scripts/secrets.sh edit apprise.server)")
    pw = os.environ.get("APPRISE_ADMIN_PASSWORD") or getpass.getpass("Admin password for the Apprise panel (hidden, 12+ characters; empty = generate): ").strip()
    if pw and not os.environ.get("APPRISE_ADMIN_PASSWORD") and getpass.getpass("Type it again to confirm: ").strip() != pw:
        die("the two entries differ: nothing was written")
    generated = False
    if not pw:
        pw, generated = secrets.token_urlsafe(18), True
    if len(pw) < 12:
        die("the password must be at least 12 characters")
    print(f"Tagged {host} with util: [notify]." if tag_host(host) else f"{host} already has util: [notify].")
    sync = subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT, capture_output=True, text=True)
    rules = open(os.path.join(ROOT, ".sops.yaml")).read() if os.path.exists(os.path.join(ROOT, ".sops.yaml")) else ""
    if sync.returncode != 0 or "secrets/apprise/server" not in rules:
        die("the encryption rules do not cover the new secret yet. Usually the framework checkout is out of date (it must contain hosts/tags/util/notify.yml): "
            "update it (git -C ../consigliere pull), then run scripts/access.sh sync and this command again.\n" + (sync.stdout + sync.stderr).strip()[-500:])
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write("---\n")
            for k, v in (("apprise_server_admin_password", pw), ("apprise_server_web_secret", secrets.token_urlsafe(48))):
                fh.write(f"{k}: {json.dumps(v)}\n")
        env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret: " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("Wrote config/secrets/apprise/server.yml (encrypted).")
    if generated:
        path = os.path.expanduser("~/.apprise-admin-password")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(pw + "\n")
        print(f"The generated admin password is in {path} (readable only by you): save it in your password manager, then delete the file.")
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nReview it, then:  git add -A && git commit -m 'notify: Apprise API' && git push\nThen: scripts/reconcile-now.sh {host}")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
