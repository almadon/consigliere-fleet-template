#!/usr/bin/env python3
"""Add (or remove) one tag value on some hosts in the host table, and check the result.

  scripts/tag.sh add <dimension> <value> [--hosts all|a,b,c] [--skip-types unraid,macos] [--dry-run]
  scripts/tag.sh remove <dimension> <value> [--hosts ...]

Example:  scripts/tag.sh add feat otel --hosts <host> --skip-types unraid
Edits config/inventory/hosts.yml only, runs scripts/access.sh sync (secret grants follow the tags) and the fleet preflight, and shows the
changes. Nothing is committed or pushed. A tag whose manifest needs a secret that does not exist yet makes those hosts fail their run:
create the secret first (the feature's own helper script does tag + secret together).
"""
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
DIMS = ("type", "org", "site", "util", "feat", "cert", "prop", "fw")


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


def items_of(block, dim):
    for ln in block:
        m = re.match(rf"^      {dim}:\s*\[(.*?)\]", ln)
        if m:
            return [x.strip() for x in m.group(1).split(",") if x.strip()]
    return []


def apply(lines, dim, value, wanted, skip, remove):
    changed, skipped = [], []
    for name, a, b in sorted(host_blocks(lines), key=lambda t: -t[1]):
        if wanted != "all" and name not in wanted:
            continue
        block = lines[a:b]
        if (field(block, "type") or "") in skip:
            skipped.append(name)
            continue
        have = items_of(block, dim)
        if remove == (value in have):
            pi = next((j for j, ln in enumerate(block) if re.match(rf"^      {dim}:\s*\[", ln)), None)
            if remove:
                new = [x for x in have if x != value]
                m = re.match(rf"^(      {dim}:\s*\[)(.*?)(\].*)$", block[pi])
                if new:
                    block[pi] = f"{m.group(1)}{', '.join(new)}{m.group(3)}"
                else:
                    del block[pi]
            elif pi is not None:
                m = re.match(rf"^(      {dim}:\s*\[)(.*?)(\].*)$", block[pi])
                inner = m.group(2).strip()
                block[pi] = f"{m.group(1)}{(inner + ', ') if inner else ''}{value}{m.group(3)}"
            else:
                ti = next((j for j, ln in enumerate(block) if re.match(r"^      type:", ln)), 0)
                block.insert(ti + 1, f"      {dim}: [{value}]")
            lines[a:b] = block
            changed.append(name)
    return changed, skipped


def main(argv):
    if len(argv) < 3 or argv[0] in ("-h", "--help") or argv[0] not in ("add", "remove"):
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    action, dim, value = argv[0], argv[1], argv[2]
    if dim not in DIMS:
        die(f"dimension must be one of {', '.join(DIMS)}")
    wanted = "all"
    if "--hosts" in argv:
        v = argv[argv.index("--hosts") + 1]
        wanted = "all" if v == "all" else [h.strip().lower() for h in v.split(",")]
    skip = set(argv[argv.index("--skip-types") + 1].split(",")) if "--skip-types" in argv else set()
    lines = open(HOSTS).read().split("\n")
    known = {n for n, _, _ in host_blocks(lines)}
    if wanted != "all" and (bad := [h for h in wanted if h not in known]):
        die(f"not in the host table: {', '.join(bad)}")
    changed, skipped = apply(lines, dim, value, wanted, skip, action == "remove")
    verb = "removed from" if action == "remove" else "added to"
    print(f"{dim}: {value} {verb}: {', '.join(reversed(changed)) or 'nobody (already as wanted)'}")
    if skipped:
        print("Skipped by --skip-types: " + ", ".join(reversed(skipped)))
    if "--dry-run" in argv or not changed:
        print("(nothing written)" if "--dry-run" in argv else "")
        return 0
    open(HOSTS, "w").write("\n".join(lines))
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "diff", "--stat"], cwd=ROOT)
    print("\nReview it, then:  git add -A && git commit -m '" + f"{dim}: {value}" + "' && git push")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
