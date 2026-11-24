#!/usr/bin/env python3
"""Exposure watch: scan the fleet's public addresses (and ask Shodan) and alert on open ports that are not declared.

  scripts/exposure.sh init [--host <host>]   tag the scanner host util: [exposure] and store your Shodan API key (asked, hidden; Enter = none)
  scripts/exposure.sh key                    replace the stored Shodan API key (asked, hidden; Enter = none)
  scripts/exposure.sh learn [--host <host>]  run a scan now and print what is open as YAML (nothing is notified): review it, then declare it
  scripts/exposure.sh check [--host <host>]  run a scan now, compare with the declared ports and print the findings (nothing is notified)
  scripts/exposure.sh run   [--host <host>]  run the scheduled job now (notifies, keeps state)

The declared ports are in config/vars/group/util_exposure.yml (exposure_watch_targets). The key is stored encrypted (config/secrets/shodan/api.yml)
and only the scanner host can read it. Run the scanner on a host OUTSIDE the networks it scans; it skips a target named like itself.
"""
import getpass
import json
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "shodan", "api.yml")


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
            if "exposure" in items:
                return False
            lines[i] = f"{m.group(1)}{', '.join(items + ['exposure'])}{m.group(3)}"
            open(HOSTS, "w").write("\n".join(lines))
            return True
    lines.insert(start + 1, "      util: [exposure]")
    open(HOSTS, "w").write("\n".join(lines))
    return True


def sops_env():
    return dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))


def ask_key():
    if "SHODAN_API_KEY" in os.environ:          # for scripts and tests
        return os.environ["SHODAN_API_KEY"].strip()
    if not sys.stdin.isatty():
        die("no terminal to ask on: run this in a terminal, or set SHODAN_API_KEY for the one command")
    return getpass.getpass("Shodan API key (hidden; Enter for none, the free InternetDB is used): ").strip()


def write_secret(key):
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(f"---\nexposure_watch_shodan_key: {json.dumps(key)}\n")
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=sops_env(), capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret: " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def on_host(host, cmd):
    return subprocess.run([os.path.join(ROOT, "scripts", "fleet-run.sh"), host, "--yes", "--", cmd]).returncode


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    mode = argv[0]
    host = argv[argv.index("--host") + 1].lower() if "--host" in argv else None
    if not host:
        die("--host <name> is required: the host that will run it")
    if mode == "init":
        print(f"Tagged {host} with util: [exposure]." if tag_host(host) else f"{host} already has util: [exposure].")
        subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(SECRET):
            print("config/secrets/shodan/api.yml already exists; to change the key: scripts/exposure.sh key")
        else:
            key = ask_key()
            write_secret(key)
            print("Stored the Shodan API key (encrypted)." if key else "No key stored: the free InternetDB will be used (add one later: scripts/exposure.sh key).")
        p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
        print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
        subprocess.run(["git", "status", "--short"], cwd=ROOT)
        print(f"\nReview it, then:  git add -A && git commit -m 'exposure watch' && git push\nThen: scripts/reconcile-now.sh {host}   and   scripts/exposure.sh learn --host {host}")
        return 0 if p.returncode == 0 else 1
    if mode == "key":
        key = ask_key()
        write_secret(key)
        print("Stored the Shodan API key (encrypted)." if key else "Key cleared: the free InternetDB will be used.")
        print("Review, commit and push; the scanner host picks it up on its next run (or: scripts/reconcile-now.sh <host>).")
        return 0
    if mode in ("learn", "check", "run"):
        flag = {"learn": " --learn", "check": " --dry-run", "run": ""}[mode]
        return on_host(host, "fleet-exposure-watch" + flag + (" 2>&1 | grep -v '^{' " if mode in ("learn", "check") else " 2>&1 | tail -20"))
    die("usage: scripts/exposure.sh init|key|learn|check|run [--host NAME]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
