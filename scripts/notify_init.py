#!/usr/bin/env python3
"""Turn on run reporting through Pushover (Apprise), in the one safe order, and leave it for you to review and push.

  scripts/notify.sh init [--hosts <host>|all|a,b,c] [--dry-run] [--replace]

A host tagged  feat: [apprise]  fails its run until the secret apprise.notify exists, and the secret can only be encrypted once
a host carries the tag. So this does everything together:
  1. asks for your Pushover user key and an application token (hidden input)
  2. adds  feat: [apprise]  to the chosen hosts (Unraid and macOS hosts are skipped: they cannot run the role)
  3. writes the shared secret config/secrets/apprise/notify.yml (encrypted for exactly those hosts): failures arrive as
     Pushover priority "high" (tag alert), recoveries and change summaries as priority "low" (tag info)
  4. runs the fleet preflight and shows the changes. Nothing is committed or pushed.

Roll out in stages: first  --hosts <host> , test with  fleet-notify "test" "hello"  on it, then  --hosts all.
--replace stores new keys without touching the host table. For scripts: PUSHOVER_USER and PUSHOVER_TOKEN replace the prompts.
"""
import getpass
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "apprise", "notify.yml")
KEY_RE = re.compile(r"^[A-Za-z0-9]{30}$")
SKIP_TYPES = {"unraid", "macos"}


def die(msg):
    sys.exit(f"ERROR: {msg}")


def host_blocks(lines):
    out, cur = [], None
    for i, ln in enumerate(lines):
        m = re.match(r"^    ([A-Za-z0-9_.-]+):\s*(#.*)?$", ln)
        if m:
            if cur:
                out.append((cur[0], cur[1], i))
            cur = (m.group(1).lower(), i)
        elif cur and re.match(r"^\S", ln) and ln.strip() and not ln.startswith("#"):
            out.append((cur[0], cur[1], i))
            cur = None
    if cur:
        out.append((cur[0], cur[1], len(lines)))
    return out


def field(block, name):
    for ln in block:
        m = re.match(rf"^      {name}:\s*(.*?)\s*(#.*)?$", ln)
        if m:
            return m.group(1)
    return None


def has_apprise(block):
    for ln in block:
        m = re.match(r"^      feat:\s*\[(.*?)\]", ln)
        if m and "apprise" in [x.strip() for x in m.group(1).split(",")]:
            return True
    return False


def plan(lines, wanted):
    todo, skipped = [], []
    for name, a, b in host_blocks(lines):
        if wanted != "all" and name not in wanted:
            continue
        if (field(lines[a:b], "type") or "") in SKIP_TYPES:
            skipped.append(name)
        elif not has_apprise(lines[a:b]):
            todo.append((name, a, b))
    return todo, skipped


def add_tag(lines, todo):
    out = list(lines)
    for name, a, b in sorted(todo, key=lambda t: -t[1]):
        block = out[a:b]
        fi = next((j for j, ln in enumerate(block) if re.match(r"^      feat:\s*\[", ln)), None)
        if fi is not None:
            m = re.match(r"^(      feat:\s*\[)(.*?)(\].*)$", block[fi])
            inner = m.group(2).strip()
            block[fi] = f"{m.group(1)}{(inner + ', ') if inner else ''}apprise{m.group(3)}"
        else:
            ti = next((j for j, ln in enumerate(block) if re.match(r"^      type:", ln)), 0)
            block.insert(ti + 1, "      feat: [apprise]")
        out[a:b] = block
    return out


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    dry, replace = "--dry-run" in argv, "--replace" in argv
    wanted = "all"
    if "--hosts" in argv:
        v = argv[argv.index("--hosts") + 1]
        wanted = "all" if v == "all" else [h.strip().lower() for h in v.split(",")]

    lines = open(HOSTS).read().split("\n")
    todo, skipped = ([], []) if replace else plan(lines, wanted)
    if skipped:
        print("Skipped (cannot run the role): " + ", ".join(skipped))
    if todo:
        print("Hosts that will get  feat: [apprise]:  " + ", ".join(n for n, _, _ in todo))
    elif not replace:
        print("Every selected host already has feat: [apprise].")
    have_secret = os.path.exists(SECRET) and not replace
    if have_secret:
        print("The secret apprise.notify already exists: keeping it, only tagging hosts and re-encrypting for them.")
    if dry:
        print("(dry run: nothing written)")
        return 0
    if have_secret and not todo:
        print("Nothing to do.")
        return 0

    if have_secret:
        open(HOSTS, "w").write("\n".join(add_tag(lines, todo)))
        subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        user = os.environ.get("PUSHOVER_USER") or getpass.getpass("Pushover user key (30 characters; hidden): ").strip()
        token = os.environ.get("PUSHOVER_TOKEN") or getpass.getpass("Pushover application token (30 characters; hidden): ").strip()
        if not KEY_RE.match(user) or not KEY_RE.match(token):
            die("a Pushover user key and an application token are each 30 letters and digits")
        if todo:
            open(HOSTS, "w").write("\n".join(add_tag(lines, todo)))
        # the encryption rule exists only once a host carries the tag, so sync first
        subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.makedirs(os.path.dirname(SECRET), exist_ok=True)
        tmp = SECRET + ".new"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write("---\napprise_notify_urls:\n"
                         f'  - "pover://{user}@{token}?priority=high":\n      - tag: alert\n'
                         f'  - "pover://{user}@{token}?priority=low":\n      - tag: info\n')
            env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
            r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env,
                               capture_output=True, text=True)
            if r.returncode != 0:
                die("could not encrypt the secret (is a host tagged, and is your admin key in place?): " + r.stderr.strip()[:200])
            os.replace(tmp, SECRET)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        print("Wrote config/secrets/apprise/notify.yml (encrypted).")

    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print("\nReview it, then:  git add -A && git commit -m 'run reporting via Pushover' && git push")
    print("Each tagged host installs fleet-notify on its next run (within ~20 minutes). Test on a host:  fleet-notify \"test\" \"hello\"")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
