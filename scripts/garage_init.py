#!/usr/bin/env python3
"""Set up Garage (S3 object store) in one safe step, and leave it for you to review and push.

  scripts/garage.sh init [--host <host>]    first setup
  scripts/garage.sh webui                   add the admin API token and the web UI's login to an EXISTING secret

init tags the host  util: [garage]  (if not already), generates the cluster secret, the admin API token and the web UI login, and stores them
encrypted as config/secrets/garage/server.yml. webui does the same for the last two when the secret was made before the web UI existed. Both
run the fleet preflight and show what changed; nothing is committed or pushed. The web UI user is "admin"; its password is generated and
kept in the same secret as garage_webui_password (read it with: scripts/secrets.sh view garage.server). The password hash needs `htpasswd`
(Apache utils; present on macOS). The data disk is named in config/vars/host/<host>.yml (data_disk_device) and is only formatted when blank.
"""
import json
import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
VARS = os.path.join(ROOT, "config", "vars", "group", "util_garage.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "garage", "server.yml")


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
            if "garage" in items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(items + ['garage'])}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return True
    lines.insert(start + 1, "      util: [garage]")
    open(HOSTS, "w").write("\n".join(lines))
    return True


def sops_env():
    return dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))


def webui_values():
    password = secrets.token_urlsafe(18)
    try:
        h = subprocess.run(["htpasswd", "-nbBC", "10", "admin", password], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        die("htpasswd is needed to hash the web UI password (Apache utils: brew install httpd / apt install apache2-utils)")
    return {"garage_admin_token": secrets.token_urlsafe(32), "garage_webui_password": password, "garage_webui_auth": h}


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


def finish(host, msg):
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print(f"\nReview it, then:  git add -A && git commit -m 'garage' && git push\n{msg}")
    return 0 if p.returncode == 0 else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    mode = argv[0]
    host = argv[argv.index("--host") + 1].lower() if "--host" in argv else None
    if not host:
        die("--host <name> is required: the host that will run it")
    if mode == "webui":
        if not os.path.exists(SECRET):
            die("config/secrets/garage/server.yml does not exist yet: run  scripts/garage.sh init")
        r = subprocess.run(["sops", "--decrypt", "--output-type", "json", SECRET], env=sops_env(), capture_output=True, text=True)
        if r.returncode != 0:
            die("could not read the secret: " + r.stderr.strip()[:200])
        data = json.loads(r.stdout)
        added = {k: v for k, v in webui_values().items() if k not in data}
        if not added:
            print("The secret already has the admin token and the web UI login: nothing to do.")
            return 0
        data.update(added)
        write_secret(data)
        print("Added to config/secrets/garage/server.yml: " + ", ".join(added) + "  (read the password: scripts/secrets.sh view garage.server)")
        return finish(host, f"{host} starts the web UI on its next run (within ~20 minutes).")
    if mode != "init":
        die("usage: scripts/garage.sh init|webui")
    if not os.path.exists(VARS):
        die("config/vars/group/util_garage.yml is missing")
    if os.path.exists(SECRET):
        die("config/secrets/garage/server.yml already exists (the cluster secret must not change once Garage has data); to add the web UI login use: scripts/garage.sh webui")

    if tag_host(host):
        print(f"Tagged {host} with util: [garage].")
    else:
        print(f"{host} already has util: [garage].")
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = {"garage_rpc_secret": secrets.token_hex(32)}
    data.update(webui_values())
    write_secret(data)
    print("Wrote config/secrets/garage/server.yml (encrypted, generated here; the web UI password: scripts/secrets.sh view garage.server).")
    return finish(host, f"{host} starts Garage on its next run (within ~20 minutes).")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
