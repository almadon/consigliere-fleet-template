#!/usr/bin/env python3
"""Roll the Beszel agent out to the fleet, in the one safe order.

A host tagged  prop: [beszel]  fails its run until the secret beszel.agent exists, and the secret can only be
encrypted once a host carries the tag. So this does everything together and leaves it for you to review and push:

  1. checks the hub answers at beszel_hub_url
  2. asks for the hub's public key (Add system dialog) and a universal token (Settings > Tokens, hidden input)
  3. adds  prop: [beszel]  to the hosts that lack it
  4. writes the shared secret  config/secrets/beszel/agent.yml  (encrypted for exactly those hosts)
  5. runs the fleet preflight and shows the diff. Nothing is committed or pushed.

  scripts/beszel-add.sh [--hosts all|a,b,c] [--dry-run] [--replace]

Roll out in stages: first  --hosts empros  (it asks for the key and token and writes the secret), then later
--hosts all  (the secret already exists, so it only tags the remaining hosts and re-encrypts for them).
--replace rotates the secret (new token or key) without touching the host table.
For scripts: BESZEL_KEY and BESZEL_TOKEN in the environment are used instead of the prompts.
"""
import getpass
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
ALLVARS = os.path.join(ROOT, "config", "vars", "group", "all.yml")
SECRET = os.path.join(ROOT, "config", "secrets", "beszel", "agent.yml")
KEY_RE = re.compile(r"^ssh-ed25519 [A-Za-z0-9+/=]{40,}( \S.*)?$")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def hub_url():
    m = re.search(r'^beszel_hub_url:\s*"?([^"\s#]+)', open(ALLVARS).read(), re.M)
    if not m:
        die("beszel_hub_url is not set in config/vars/group/all.yml")
    return m.group(1).rstrip("/")


def host_blocks(lines):
    """[(name, start, end)] for each host under all.hosts (keys indented exactly 4 spaces)."""
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


def has_beszel(block):
    for ln in block:
        m = re.match(r"^      prop:\s*\[(.*)\]", ln)
        if m and "beszel" in [x.strip() for x in m.group(1).split(",")]:
            return True
    return False


def plan(lines, wanted):
    todo = []
    for name, a, b in host_blocks(lines):
        if wanted != "all" and name not in wanted:
            continue
        if not has_beszel(lines[a:b]):
            todo.append((name, a, b))
    return todo


def add_tag(lines, todo):
    out = list(lines)
    for name, a, b in sorted(todo, key=lambda t: -t[1]):          # bottom-up so line numbers stay valid
        block = out[a:b]
        pi = next((j for j, ln in enumerate(block) if re.match(r"^      prop:\s*\[", ln)), None)
        if pi is not None:                                           # extend an existing prop list
            ln = block[pi]
            m = re.match(r"^(      prop:\s*\[)(.*?)(\].*)$", ln)
            inner = m.group(2).strip()
            block[pi] = f"{m.group(1)}{(inner + ', ') if inner else ''}beszel{m.group(3)}"
        else:                                                        # new line right after type:, else after the key
            ti = next((j for j, ln in enumerate(block) if re.match(r"^      type:", ln)), 0)
            block.insert(ti + 1, "      prop: [beszel]")
        out[a:b] = block
    return out


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    dry = "--dry-run" in argv
    replace = "--replace" in argv
    wanted = "all"
    if "--hosts" in argv:
        v = argv[argv.index("--hosts") + 1]
        wanted = "all" if v == "all" else [h.strip().lower() for h in v.split(",")]

    url = hub_url()
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=10) as r:
            print(f"Hub answers at {url} (HTTP {r.status}).")
    except Exception as e:  # noqa: BLE001
        die(f"the hub does not answer at {url}/api/health ({e}). Is it running, and is the DNS record in place?")

    lines = open(HOSTS).read().split("\n")
    todo = [] if replace else plan(lines, wanted)
    if replace:
        print("Rotating the secret only; the host table is left alone.")
    elif todo:
        print("Hosts that will get  prop: [beszel]:  " + ", ".join(n for n, _, _ in todo))
    else:
        print("Every selected host already has prop: [beszel].")
    have_secret = os.path.exists(SECRET) and not replace
    if have_secret:
        print("The secret beszel.agent already exists: keeping it, only tagging hosts and re-encrypting for them.")
    if dry:
        print("(dry run: nothing written)")
        return 0
    if have_secret and not todo:
        print("Nothing to do.")
        return 0

    if have_secret:
        new = add_tag(lines, todo)
        open(HOSTS, "w").write("\n".join(new))
        subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
        print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
        subprocess.run(["git", "diff", "--stat"], cwd=ROOT)
        print("\nReview it, then:  git add -A && git commit -m 'beszel agents' && git push")
        return 0 if p.returncode == 0 else 1

    key = os.environ.get("BESZEL_KEY") or input("Hub public key (Add system dialog; starts with ssh-ed25519): ").strip()
    if not KEY_RE.match(key):
        die("that does not look like an ssh-ed25519 public key")
    token = os.environ.get("BESZEL_TOKEN") or getpass.getpass("Universal token (Settings > Tokens; hidden): ").strip()
    if len(token) < 8:
        die("the token looks too short")

    if todo:
        new = add_tag(lines, todo)
        open(HOSTS, "w").write("\n".join(new))
    # the encryption rule exists only once a host carries the tag, so sync first
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync", "--no-update"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.makedirs(os.path.dirname(SECRET), exist_ok=True)
    tmp = SECRET + ".new"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(f'---\nbeszel_agent_key: "{key}"\nbeszel_agent_token: "{token}"\n')
        env = dict(os.environ, SOPS_AGE_KEY_FILE=os.environ.get("SOPS_AGE_KEY_FILE", os.path.expanduser("~/.config/sops/age/keys.txt")))
        r = subprocess.run(["sops", "--encrypt", "--in-place", "--filename-override", SECRET, tmp], env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            die("could not encrypt the secret (is a host tagged, and is your admin key in place?): " + r.stderr.strip()[:200])
        os.replace(tmp, SECRET)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("Wrote config/secrets/beszel/agent.yml (encrypted).")

    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "diff", "--stat"], cwd=ROOT)
    print("\nReview it, then:  git add -A && git commit -m 'beszel agents' && git push")
    print("Every tagged host installs the agent on its next run (within ~20 minutes), and appears in the hub by itself.")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
