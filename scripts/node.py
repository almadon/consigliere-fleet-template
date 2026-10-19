#!/usr/bin/env python3
"""Add or change a node by answering questions. No YAML editing.

  scripts/node.sh add [name]       a new node: asks what it is and what it should run, writes hosts.yml (and its vars
                                   file), checks the result, shows the steps to run on the node, and can finish the
                                   registration when the node prints its age key
  scripts/node.sh edit <name>      change what an existing node runs (the same questions, with the current answers)
  scripts/node.sh key <name> [age-key]
                                   finish a node's registration: store its age key, re-encrypt its secrets, commit, push

Every question has a default (press Enter). Nothing is committed or pushed without asking. Ctrl-C at any point
leaves the files exactly as they were until the "Write it?" question.
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import access as A  # noqa: E402

ROOT = A.ROOT
HOSTS = A.HOSTS
VARS_HOST = os.path.join(ROOT, "config", "vars", "host")
FRAMEWORK_URL = os.environ.get("FRAMEWORK_REPO_URL", "https://github.com/almadon/Consigliere.git")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ORDER = ["type", "org", "site", "util", "feat", "cert", "prop", "fw"]
TYPES = [("lxc", "an LXC container (Proxmox)"), ("vps", "a virtual private server"), ("vm", "a virtual machine"),
         ("metal", "a physical machine"), ("unraid", "an Unraid server (runs the reconciler in a container)")]

# What a node can be asked to do: label, how it shows up in hosts.yml, and a short explanation.
FEATURES = [
    ("docker", "Runs Docker apps", ("util", "docker"), "also gets the Arcane agent"),
    ("arkeep", "Backed up by Arkeep (agent)", ("feat", "arkeep"), "the fleet standard"),
    ("beszel", "Monitored by Beszel", ("prop", "beszel"), "the fleet standard; needs the hub secret"),
    ("web", "Serves websites to the internet (Traefik)", ("util", "traefik"), "opens ports 80 and 443"),
    ("restic", "A restic backup server", ("util", "restic"), "a storage target for Arkeep"),
]


# ------------------------------------------------------------------------------------------------ prompting
def ask(prompt, default=None, check=None):
    while True:
        raw = input(f"{prompt}" + (f" [{default}]" if default not in (None, "") else "") + ": ").strip()
        val = raw or (default or "")
        if check:
            err = check(val)
            if err:
                print(f"  {err}")
                continue
        return val


def confirm(prompt, default=False):
    d = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{d}]: ").strip().lower()
    return default if not raw else raw.startswith("y")


def choose(prompt, options, default=None):
    """options: [(value, description)]. Returns the value."""
    print(prompt)
    for i, (v, d) in enumerate(options, 1):
        print(f"  {i}) {v:8} {d}")
    dflt = next((i for i, (v, _) in enumerate(options, 1) if v == default), None)
    while True:
        raw = input(f"Choose 1-{len(options)}" + (f" [{dflt}]" if dflt else "") + ": ").strip()
        if not raw and dflt:
            return options[dflt - 1][0]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        if raw in [v for v, _ in options]:
            return raw
        print("  pick one of the numbers above")


def checklist(prompt, items, selected):
    """items: [(key, label, note)]. Returns the chosen keys. Type numbers to toggle, Enter to accept."""
    sel = set(selected)
    while True:
        print(prompt)
        for i, (k, label, note) in enumerate(items, 1):
            print(f"  [{'x' if k in sel else ' '}] {i}) {label}" + (f"   ({note})" if note else ""))
        raw = input("Toggle by number (e.g. 1 3), Enter when done: ").strip()
        if not raw:
            return [k for k, _, _ in items if k in sel]
        for tok in raw.replace(",", " ").split():
            if tok.isdigit() and 1 <= int(tok) <= len(items):
                k = items[int(tok) - 1][0]
                sel.symmetric_difference_update({k})


# ------------------------------------------------------------------------------------------------ the host table
def read_lines():
    return open(HOSTS).read().split("\n")


def table():
    return (A.load(HOSTS, {}).get("all", {}) or {}).get("hosts", {}) or {}


def blocks(lines):
    out, cur = {}, None
    for i, ln in enumerate(lines):
        m = re.match(r"^    ([A-Za-z0-9_.-]+):\s*(#.*)?$", ln)
        if m:
            if cur:
                out[cur[0]] = (cur[1], i)
            cur = (m.group(1).lower(), i)
        elif cur and ln.strip() and re.match(r"^\S", ln) and not ln.startswith("#"):
            out[cur[0]] = (cur[1], i)
            cur = None
    if cur:
        out[cur[0]] = (cur[1], len(lines))
    return out


def set_key(lines, name, key, values):
    """Set (or remove, when values is empty) one list/scalar key in a host's block."""
    a, b = blocks(lines)[name]
    block = lines[a:b]
    idx = next((j for j, ln in enumerate(block) if re.match(rf"^      {key}:", ln)), None)
    if not values:
        if idx is not None:
            del block[idx]
    else:
        text = f"      {key}: {values}" if isinstance(values, str) else f"      {key}: [{', '.join(values)}]"
        if idx is not None:
            comment = re.search(r"(\s+#.*)$", block[idx])
            block[idx] = text + (comment.group(1) if comment and "[" in block[idx] else "")
        else:   # keep the canonical order
            after = ORDER.index(key)
            pos = 1
            for j, ln in enumerate(block):
                m = re.match(r"^      ([a-z]+):", ln)
                if m and m.group(1) in ORDER and ORDER.index(m.group(1)) < after:
                    pos = j + 1
            block.insert(pos, text)
    lines[a:b] = block
    return lines


def entry_text(name, vals, comment=""):
    out = [f"    {name}:" + (f"                       # {comment}" if comment else "")]
    for key in ORDER:
        v = vals.get(key)
        if not v:
            continue
        out.append(f"      {key}: {v}" if isinstance(v, str) else f"      {key}: [{', '.join(v)}]")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ steps
def secret_exists(scope):
    return os.path.exists(os.path.join(ROOT, A.scope_file(scope)))


def tailnet_peer(name):
    try:
        import audit
        for p in audit.tailnet():
            if p["name"] == name:
                return p
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001
        pass
    return None


def values_from_features(chosen, certs):
    vals = {"util": [], "feat": [], "prop": [], "cert": list(certs)}
    for key, _label, (dim, val), _n in FEATURES:
        if key in chosen:
            vals[dim].append(val)
    return vals


def features_of(h):
    chosen = []
    for key, _label, (dim, val), _n in FEATURES:
        if val in (h.get(dim) or []):
            chosen.append(key)
    return chosen


def fleet_ssh_url():
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if not url:
            remotes = subprocess.run(["git", "remote"], cwd=ROOT, capture_output=True, text=True).stdout.split()
            url = subprocess.run(["git", "remote", "get-url", remotes[0]], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        url = ""
    m = re.match(r"https://github.com/(.+?)(\.git)?$", url)
    return f"git@github.com:{m.group(1)}.git" if m else (url or "git@github.com:<you>/<fleet>.git")


def missing_cert_secrets(certs):
    return [c for c in certs if not os.path.exists(os.path.join(ROOT, "config", "secrets", "cw", f"{c}.yml"))]


def warn_cert_secrets(name, certs):
    """A host with a cert: tag whose secret does not exist fails its run, so never offer to push in that state."""
    miss = missing_cert_secrets(certs)
    if not miss:
        return False
    print("\nBefore this can be pushed, each certificate needs its Cert Warden keys stored (a host with a cert tag but no "
          "secret fails its run).\nThe tag is written locally now, so these work:")
    for c in miss:
        print(f"  scripts/cw-add.sh {c} <that Cert Warden's URL>")
    print("Then commit and push everything together:  git add -A && git commit -m 'add: " + name + "' && git push")
    return True


def validate_and_show(touched):
    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    ok = p.returncode == 0
    print("Check (preflight):", "ok" if ok else "FAILED\n" + (p.stdout + p.stderr)[-700:])
    subprocess.run(["git", "status", "--short"] + touched, cwd=ROOT)
    return ok


def commit_push(message):
    subprocess.run(["git", "add", "-A"], cwd=ROOT)
    subprocess.run(["git", "commit", "-q", "-m", message + "\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], cwd=ROOT)
    r = subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, text=True)
    print((r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "pushed")
    return r.returncode == 0


def node_steps(name, typ, docker):
    print(f"\nNow on the NODE ({name}), as root:")
    n = 1
    print(f" {n}. Name it exactly like this:   hostnamectl set-hostname {name}"); n += 1
    if typ == "lxc":
        print(f" {n}. LXC only: in Proxmox, give the container /dev/net/tun (copy the lines from an existing node's /etc/pve/lxc/<id>.conf)\n"
              "    and enable nesting if it will run Docker, then restart the container."); n += 1
    if typ == "unraid":
        print(f" {n}. Unraid: install the Tailscale plugin and join the tailnet first (see hosts/bootstrap/unraid/README.md)."); n += 1
    else:
        print(f" {n}. Join the tailnet with a TAGGED, one-off auth key (the node must show up as '{name}' in the Tailscale admin console)."); n += 1
    print(f" {n}. Run the bootstrap (it detects Debian/Ubuntu, Unraid or macOS by itself):"); n += 1
    print(f"      curl -fsSLO https://raw.githubusercontent.com/almadon/Consigliere/main/hosts/bootstrap/bootstrap.sh")
    print(f"      FRAMEWORK_REPO_URL={FRAMEWORK_URL} \\\n      FLEET_CONFIG_REPO_URL={fleet_ssh_url()} \\\n      bash bootstrap.sh")
    print(f" {n}. It prints a deploy key (add it as READ-ONLY on the fleet repo) and then an age key (age1...).")
    print(f"    Back here: scripts/node.sh key {name}   (paste the age key; it registers, re-encrypts, commits and pushes)")


# ------------------------------------------------------------------------------------------------ commands
def pick_features(defaults, secret_ok):
    items = [(k, label, note + ("" if k != "beszel" or secret_ok else "; the hub secret does not exist yet, so it is written commented-out"))
             for k, label, _t, note in FEATURES]
    return checklist("\nWhat should this node do?", items, defaults)


def common_questions(existing=None):
    h = existing or {}
    typ = choose("\nWhat kind of node is it?", TYPES, h.get("type") or "lxc") if not existing else h.get("type")
    orgs = sorted({str(v.get("org")) for v in table().values() if v and v.get("org")})
    sites = sorted({str(v.get("site")) for v in table().values() if v and v.get("site")})
    org = ask(f"Organisation{' (' + ', '.join(orgs) + ')' if orgs else ''}; Enter for none", str(h.get("org") or ""))
    site = ask(f"Site{' (' + ', '.join(sites) + ')' if sites else ''}; Enter if not needed", str(h.get("site") or ""))
    return typ, org, site


def build_vals(typ, org, site, chosen, certs, secret_ok, existing=None):
    vals = values_from_features(chosen, certs)
    vals["type"], vals["org"], vals["site"] = typ, org, site
    vals["fw"] = list((existing or {}).get("fw") or [])
    if "web" in chosen:
        vals["fw"] = [x for x in vals["fw"] if x not in ("http", "https")]   # util: traefik already implies them
    if "beszel" in chosen and not secret_ok:   # a host with the tag fails its run until the shared secret exists
        vals["prop"] = [x for x in vals["prop"] if x != "beszel"]
    return vals


def cmd_add(argv):
    name = (argv[0] if argv else ask("Node name (its Tailscale hostname, lowercase)", None, lambda v: None if NAME_RE.match(v) else "letters, digits and dashes, lowercase")).lower()
    if not NAME_RE.match(name):
        sys.exit("ERROR: the name must be lowercase letters, digits and dashes.")
    if name in {str(k).lower() for k in table()}:
        print(f"{name} is already in the fleet. Use:  scripts/node.sh edit {name}")
        return 2
    peer = tailnet_peer(name)
    if peer:
        print(f"{name} is already on the tailnet ({peer['os'] or '?'}, {'online' if peer['online'] else 'offline'}, {peer['ip']}).")
    else:
        print(f"{name} is not on the tailnet yet; that comes in the steps at the end.")
    typ, org, site = common_questions()
    secret_ok = secret_exists("beszel.agent")
    std = {s["feature"] for s in A.load(os.path.join(ROOT, "config", "standards.yml"), {}).get("standards", [])}
    defaults = [k for k, f in (("arkeep", "arkeep_agent"), ("beszel", "beszel_agent")) if f in std or not std]
    chosen = pick_features(defaults, secret_ok)
    certs = []
    if "web" in chosen:
        raw = ask("Certificate names this node should fetch from Cert Warden (comma separated, Enter for none)", "")
        certs = [c.strip() for c in raw.split(",") if c.strip()]
    vals = build_vals(typ, org, site, chosen, certs, secret_ok)
    comment = ask("A short note for the host table (Enter for none)", "")
    token = None
    if "docker" in chosen:
        token = ask("Arcane agent token for this node (mint one in the Arcane manager; Enter to add it later)", "")

    print("\nThis will be written to config/inventory/hosts.yml:\n")
    print(entry_text(name, vals, comment))
    if "beszel" in chosen and not secret_ok:
        print("      # prop: [beszel]            # enable after: scripts/beszel-add.sh --hosts " + name)
    if token:
        print(f"\nand config/vars/host/{name}.yml will hold the Arcane token.")
    if not confirm("\nWrite it?", True):
        print("Nothing written.")
        return 0

    text = "\n".join(read_lines()).rstrip("\n") + "\n" + entry_text(name, vals, comment) + "\n"
    if "beszel" in chosen and not secret_ok:
        text += "      # prop: [beszel]            # enable after: scripts/beszel-add.sh --hosts " + name + "\n"
    backup = open(HOSTS).read()
    open(HOSTS, "w").write(text)
    if name not in {str(k).lower() for k in table()}:
        open(HOSTS, "w").write(backup)
        sys.exit("ERROR: the result did not parse as expected; hosts.yml was restored.")
    touched = ["config/inventory/hosts.yml"]
    if token:
        os.makedirs(VARS_HOST, exist_ok=True)
        vp = os.path.join(VARS_HOST, f"{name}.yml")
        if not os.path.exists(vp):
            open(vp, "w").write(f'---\narcane_agent_token: "{token}"\n')
            touched.append(f"config/vars/host/{name}.yml")
    ok = validate_and_show(touched)
    if not ok:
        print("Fix the problem above (the wizard changed only the files listed).")
        return 1
    held = warn_cert_secrets(name, certs)
    if not held and confirm("Commit and push this now?", False):
        commit_push(f"add: {name} (wizard)")
    node_steps(name, typ, "docker" in chosen)
    if "docker" in chosen and not token:
        print(f"\nArcane: mint a token for {name} in the Arcane manager, then run  scripts/node.sh edit {name}  or put arcane_agent_token in config/vars/host/{name}.yml.")
    return 0


def cmd_edit(argv):
    if not argv:
        sys.exit("usage: scripts/node.sh edit <name>")
    name = argv[0].lower()
    t = {str(k).lower(): v or {} for k, v in table().items()}
    if name not in t:
        print(f"{name} is not in the fleet. Use:  scripts/node.sh add {name}")
        return 2
    h = t[name]
    print(f"{name}: type {h.get('type', '-')}, org {h.get('org', '-')}, site {h.get('site', '-')}")
    secret_ok = secret_exists("beszel.agent")
    items = [(k, label, note) for k, label, _t, note in FEATURES]
    chosen = checklist("\nWhat should it do? (checked = it does today)", items, features_of(h))
    certs = list(h.get("cert") or [])
    if "web" in chosen:
        raw = ask("Certificate names (comma separated)", ", ".join(certs))
        certs = [c.strip() for c in raw.split(",") if c.strip()]
    elif certs:
        certs = certs if confirm(f"It keeps its certificates {certs}. Keep them?", True) else []
    new = values_from_features(chosen, certs)
    new["fw"] = list(h.get("fw") or [])
    if "beszel" in chosen and not secret_ok:
        new["prop"] = [x for x in new["prop"] if x != "beszel"]
        print("(Beszel: the hub secret does not exist yet, so that tag is not written; run scripts/beszel-add.sh --hosts " + name + ")")
    # keep tags the wizard does not manage (for example other util/feat/prop values)
    managed = {v for _, _, (_d, v), _ in FEATURES}
    for dim in ("util", "feat", "prop"):
        extra = [x for x in (h.get(dim) or []) if x not in managed]
        new[dim] = extra + new[dim]
    lines = read_lines()
    changes = []
    for dim in ("util", "feat", "cert", "prop"):
        old = list(h.get(dim) or [])
        if sorted(old) != sorted(new[dim]):
            lines = set_key(lines, name, dim, new[dim])
            changes.append(f"  {dim}: {old or '-'}  ->  {new[dim] or '-'}")
    if not changes:
        print("No changes.")
        return 0
    print("\nChanges to " + name + ":\n" + "\n".join(changes))
    if not confirm("\nWrite them?", True):
        print("Nothing written.")
        return 0
    backup = open(HOSTS).read()
    open(HOSTS, "w").write("\n".join(lines))
    if name not in {str(k).lower() for k in table()}:
        open(HOSTS, "w").write(backup)
        sys.exit("ERROR: the result did not parse as expected; hosts.yml was restored.")
    # new tags can mean new secrets for this host: refresh the encryption rules
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync"], cwd=ROOT, capture_output=True)
    ok = validate_and_show(["config/inventory/hosts.yml", ".sops.yaml", "config/secrets"])
    held = warn_cert_secrets(name, certs)
    if ok and not held and confirm("Commit and push this now?", False):
        commit_push(f"{name}: change what it runs (wizard)")
    return 0 if ok else 1


def cmd_key(argv):
    if not argv:
        sys.exit("usage: scripts/node.sh key <name> [age-key]")
    name = argv[0].lower()
    if name not in {str(k).lower() for k in table()}:
        sys.exit(f"ERROR: {name} is not in hosts.yml (scripts/node.sh add {name} first).")
    key = argv[1] if len(argv) > 1 else ask("The age key the node printed (age1...)", None, lambda v: None if A.AGE_RE.match(v) else "that is not an age public key (age1 followed by 50+ letters/digits)")
    r = subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "add-host", name, key], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR: " + (r.stderr or r.stdout).strip()[-300:])
    subprocess.run([os.path.join(ROOT, "scripts", "access.sh"), "sync"], cwd=ROOT, capture_output=True)
    ok = validate_and_show(["config/access.yml", ".sops.yaml", "config/secrets"])
    if ok and confirm("Commit and push this now?", True):
        commit_push(f"add: {name} age key (wizard)")
        print(f"\nBack on the node, press Enter: it applies its first run. Then:  scripts/audit.sh node {name}")
    return 0 if ok else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        return {"add": cmd_add, "edit": cmd_edit, "key": cmd_key}.get(cmd, lambda _a: (print(__doc__), 2)[1])(rest)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Anything not yet written was not changed.")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
