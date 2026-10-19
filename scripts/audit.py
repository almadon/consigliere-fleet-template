#!/usr/bin/env python3
"""What does each node have, and what is it missing?

Everything here is read-only. It compares what hosts.yml and the tag manifests DECLARE with your standards
(config/standards.yml) and, with `live`, with what the tailnet and the hosts actually show.

  scripts/audit.sh                         a table: every host x every feature, plus the gaps against your standards
  scripts/audit.sh missing <feature>       hosts without it (beszel, arcane, arkeep, traefik, or any role name), and how to fix each
  scripts/audit.sh node <name>             everything declared about one host
  scripts/audit.sh live [--ssh]            tailnet vs hosts.yml: nodes nobody manages, hosts that are gone; --ssh also checks
                                           that the declared containers really run and the last reconcile succeeded
  scripts/audit.sh onboard <name> [--type lxc|vps|vm|metal|unraid] [--docker] [--write]
                                           the exact entry and steps for a new node

For --ssh the tool runs plain `ssh root@<tailscale-ip>`; put extra options in AUDIT_SSH_OPTS
(for example AUDIT_SSH_OPTS="-o IdentitiesOnly=yes -i ~/.ssh/fleet_admin.pub").
"""
import json
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import access as A  # noqa: E402  (reuses its loading and manifest resolution)

yaml = A.yaml
ROOT = A.ROOT
STANDARDS = os.path.join(ROOT, "config", "standards.yml")

# What a feature is called to people, the role that implements it, the container that proves it runs, and how to add it.
FEATURES = {
    "arkeep_agent": {"label": "Arkeep", "container": "arkeep-agent",
                     "how": ["add  feat: [arkeep]  to {host} in config/inventory/hosts.yml",
                             "the host's age key must be registered (scripts/access.sh add-host {host} <key>), then scripts/access.sh sync"]},
    "arcane_agent": {"label": "Arcane", "container": "arcane-edge-agent",
                     "how": ["a host with  util: [docker]  gets the Arcane agent by itself; otherwise add  feat: [arcane]  to {host}",
                             "in the Arcane manager (arc.a64.one) add an edge agent for {host} and copy its token",
                             "put  arcane_agent_token: arc_...  in config/vars/host/{host}.yml  (start from empros.yml)",
                             "or set  arcane_agent_skip: true  there if this host must not run the agent"]},
    "beszel_agent": {"label": "Beszel", "container": "beszel-agent",
                     "how": ["add  prop: [beszel]  to {host} in config/inventory/hosts.yml",
                             "the shared secret beszel.agent must exist (hub public key + universal token): scripts/secrets.sh create beszel.agent",
                             "beszel_hub_url must be set (config/vars/group/all.yml)"]},
    "traefik_server": {"label": "Traefik", "container": "traefik",
                       "how": ["add  util: [traefik]  to {host}; see runbooks/cutover-caddy-to-traefik.md"]},
    "restic_server": {"label": "restic", "container": "restic-server",
                      "how": ["add  util: [restic]  to {host}"]},
    "certwarden_agent": {"label": "CertW", "container": None,
                         "how": ["add  cert: [<certificate name>]  to {host} (implies the agent)"]},
    "wazuh_agent": {"label": "Wazuh", "container": None,
                    "how": ["add  feat: [wazuh]  to {host}"]},
}
ALIASES = {"arkeep": "arkeep_agent", "arcane": "arcane_agent", "beszel": "beszel_agent", "traefik": "traefik_server",
           "restic": "restic_server", "certwarden": "certwarden_agent", "wazuh": "wazuh_agent"}


# ---------------------------------------------------------------------------------------------------------- loading
def declared():
    access = A.load(A.ACCESS, {})
    fw = A.framework_dir(access)
    resolve = A.resolver(fw)
    allvars = A.load(os.path.join(ROOT, "config", "vars", "group", "all.yml"), {})
    dims = allvars.get("fleet_tag_dimensions", ["util", "feat", "cert", "prop", "fw"])
    dirs = [os.path.join(ROOT, "config", "tags"), os.path.join(fw, "hosts", "tags")]
    table = (A.load(A.HOSTS, {}).get("all", {}) or {}).get("hosts", {}) or {}
    keys = {str(k).lower(): v for k, v in (access.get("hosts", {}) or {}).items()}
    hosts = {}
    for name, vals in table.items():
        n = str(name).lower()
        vals = vals or {}
        res = resolve(vals, dims, dirs)
        hv = A.load(os.path.join(ROOT, "config", "vars", "host", f"{n}.yml"), {})
        roles = [p["name"] for p in res["plan"] if p.get("kind") == "role"]
        hosts[n] = {"values": vals, "roles": roles, "tags": res["tags"], "secrets": res["secrets"],
                    "firewall": res["firewall"], "unknown": res["unknown"], "hostvars": hv, "key": n in keys}
    return hosts, resolve, dims, dirs, fw


def standards():
    data = A.load(STANDARDS, {})
    out = data.get("standards")
    if out:
        return out
    return [{"feature": "arkeep_agent", "applies": "all"},
            {"feature": "beszel_agent", "applies": "all"},
            {"feature": "arcane_agent", "applies": "docker"}]


def applies(std, h):
    a = std.get("applies", "all")
    util = h["values"].get("util") or []
    typ = h["values"].get("type")
    if typ in (std.get("exclude_types") or []):
        return False
    if a == "docker":
        return "docker" in util
    return True


def secret_exists(scope):
    return os.path.exists(os.path.join(ROOT, A.scope_file(scope)))


def problem(feature, name, h):
    """Why a feature that IS declared will nevertheless not work on this host (None when it will)."""
    hv = h["hostvars"]
    if not h["key"]:
        return "host has no age key registered (scripts/access.sh add-host)"
    if feature == "arcane_agent":
        if hv.get("arcane_agent_skip"):
            return "skipped on purpose (arcane_agent_skip)"
        tok = str(hv.get("arcane_agent_token", ""))
        if not tok or "CHANGEME" in tok:
            return f"no agent token yet (arcane_agent_token in config/vars/host/{name}.yml)"
    if feature == "beszel_agent" and not secret_exists("beszel.agent"):
        return "secret beszel.agent does not exist yet"
    return None


def state(feature, name, h):
    """'ok', 'inert:<why>' or 'no'."""
    if feature not in h["roles"]:
        return "no", None
    why = problem(feature, name, h)
    return ("inert", why) if why else ("ok", None)


def want_features(hosts):
    present = []
    for h in hosts.values():
        for r in h["roles"]:
            if r in FEATURES and r not in present:
                present.append(r)
    for s in standards():
        if s["feature"] not in present:
            present.append(s["feature"])
    order = list(FEATURES)
    return sorted(present, key=lambda r: order.index(r) if r in order else 99)


def resolve_feature(word):
    return ALIASES.get(word, word)


# ---------------------------------------------------------------------------------------------------------- commands
SYM = {"ok": "yes", "inert": "NO*", "no": "-"}


def cmd_matrix(hosts):
    feats = want_features(hosts)
    head = f"{'host':12} {'type':7} {'org':6} {'age key':8} " + " ".join(f"{FEATURES.get(f, {}).get('label', f)[:7]:7}" for f in feats)
    print(head)
    print("-" * len(head))
    notes, gaps = [], []
    stds = {s["feature"]: s for s in standards()}
    for n in sorted(hosts):
        h = hosts[n]
        row = f"{n:12} {str(h['values'].get('type', '-')):7} {str(h['values'].get('org', '-')):6} {'yes' if h['key'] else 'MISSING':8} "
        cells = []
        for f in feats:
            st, why = state(f, n, h)
            cells.append(f"{SYM[st]:7}")
            if st == "inert":
                notes.append(f"  * {n}: {FEATURES.get(f, {}).get('label', f)} is declared but will not work: {why}")
            if f in stds and applies(stds[f], h) and st != "ok":
                gaps.append((n, f, st, why))
        print(row + " ".join(cells))
    print("\nyes = declared and ready   NO* = declared but inert (see below)   - = not declared")
    for ln in notes:
        print(ln)
    if gaps:
        print("\nGaps against config/standards.yml:")
        for n, f, st, why in gaps:
            print(f"  {n:12} lacks {FEATURES.get(f, {}).get('label', f)}" + (f": {why}" if why else ""))
        print("\nDetails and the fix for one feature:  scripts/audit.sh missing <feature>")
    else:
        print("\nNo gaps against the standards.")


def cmd_missing(hosts, word):
    f = resolve_feature(word)
    if f not in FEATURES and not any(f in h["roles"] for h in hosts.values()):
        print(f"Unknown feature '{word}'. Known: {', '.join(sorted(ALIASES))} (or any role name).")
        return 2
    label = FEATURES.get(f, {}).get("label", f)
    std = next((s for s in standards() if s["feature"] == f), None)
    lacking = []
    for n in sorted(hosts):
        st, why = state(f, n, hosts[n])
        if st != "ok":
            lacking.append((n, st, why, bool(std) and applies(std, hosts[n])))
    have = [n for n in sorted(hosts) if state(f, n, hosts[n])[0] == "ok"]
    print(f"{label} is working on {len(have)} host(s): {', '.join(have) or '-'}\n")
    if not lacking:
        print("Every managed host has it.")
        return 0
    print(f"{label} is missing or inert on {len(lacking)} host(s):\n")
    for n, st, why, expected in lacking:
        tag = "expected by your standards" if expected else "not required by your standards"
        print(f"  {n}  ({hosts[n]['values'].get('type', '-')}; {tag})")
        print(f"    state: {'declared but inert: ' + why if st == 'inert' else 'not declared'}")
        print("    to add it:")
        steps = FEATURES.get(f, {}).get("how", ["see the role's README"])
        if st == "inert":
            steps = [f"fix: {why}"]
        for i, s in enumerate(steps, 1):
            print(f"      {i}. {s.format(host=n)}")
        print()
    print("Then: scripts/preflight.sh --strict && git add -A && git commit && git push. The host picks it up on its next run.")
    return 0


def cmd_node(hosts, name):
    n = name.lower()
    if n not in hosts:
        print(f"{n} is not in config/inventory/hosts.yml. To add it: scripts/audit.sh onboard {n}")
        return 2
    h = hosts[n]
    v = h["values"]
    print(f"{n}: {v.get('type', '-')}, org {v.get('org', '-')}, site {v.get('site', '-')}")
    print(f"  age key        {'registered' if h['key'] else 'MISSING (scripts/access.sh add-host)'}")
    for dim in ("util", "feat", "cert", "prop", "fw"):
        if v.get(dim):
            print(f"  {dim:14} {', '.join(map(str, v[dim]))}")
    print(f"  tags (with implied)  {', '.join(h['tags']) or '-'}")
    if h["unknown"]:
        print(f"  tags without a manifest (just classes): {', '.join(h['unknown'])}")
    print(f"  roles that run       {', '.join(h['roles']) or '-'}")
    for f in want_features({n: h}):
        st, why = state(f, n, h)
        if st != "no":
            print(f"    {FEATURES.get(f, {}).get('label', f):8} {'ready' if st == 'ok' else 'INERT: ' + str(why)}")
    sc = sorted(h["secrets"])
    print(f"  secrets it reads     " + (", ".join(f"{s}{'' if secret_exists(s) else ' (NOT CREATED)'}" for s in sc) or "-"))
    ports = [f"{r['port']}/{r.get('proto', 'tcp')}" for r in h["firewall"]]
    print(f"  open to the internet {', '.join(ports) or 'nothing (tailnet only)'}")
    own = sorted(k for k in h["hostvars"] if not str(k).startswith("traefik_server_routes"))
    if own:
        print(f"  host variables       {', '.join(own)}")
    routes = [k for k in h["hostvars"] if str(k).startswith("traefik_server_routes")]
    if routes:
        print(f"  proxy routes         {sum(len(h['hostvars'][k]) for k in routes)}")
    return 0


def tailnet():
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15)
        data = json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"ERROR: could not read the tailnet (tailscale status --json): {e}")
    peers = []
    for p in list((data.get("Peer") or {}).values()) + [data.get("Self") or {}]:
        ips = [i for i in p.get("TailscaleIPs", []) if ":" not in i]
        peers.append({"name": str(p.get("HostName", "")).lower(), "os": p.get("OS", ""), "online": p.get("Online"),
                      "ip": ips[0] if ips else "", "tags": p.get("Tags") or [], "last": p.get("LastSeen", "")})
    return peers


def ssh(ip, cmd):
    opts = shlex.split(os.environ.get("AUDIT_SSH_OPTS", ""))
    try:
        r = subprocess.run(["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
                            *opts, f"root@{ip}", cmd], capture_output=True, text=True, timeout=40)
        return r.returncode, r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return 255, str(e)


def cmd_live(hosts, with_ssh):
    peers = tailnet()
    byname = {p["name"]: p for p in peers}
    print("Tailnet nodes that are NOT in hosts.yml (nobody manages them):")
    unmanaged = [p for p in peers if p["name"] not in hosts]
    for p in sorted(unmanaged, key=lambda x: x["name"]):
        status = "online" if p["online"] else "offline"
        kind = {"linux": "Linux (can be onboarded: scripts/audit.sh onboard " + p["name"] + ")", "macOS": "macOS", "iOS": "iOS (not manageable)",
                "windows": "Windows (not supported)"}.get(p["os"], p["os"] or "?")
        print(f"  {p['name']:14} {status:8} {kind}")
    if not unmanaged:
        print("  none")
    print("\nHosts in hosts.yml that are not on the tailnet:")
    gone = [n for n in sorted(hosts) if n not in byname]
    print("".join(f"  {n}\n" for n in gone) or "  none")
    print("\nHosts in hosts.yml that are offline right now:")
    off = [n for n in sorted(hosts) if n in byname and not byname[n]["online"]]
    print("".join(f"  {n}\n" for n in off) or "  none")
    if not with_ssh:
        print("\n(add --ssh to also check, on each online host, that the declared containers run and the last reconcile succeeded)")
        return 0
    print("\nDeclared versus running (over SSH):")
    for n in sorted(hosts):
        p = byname.get(n)
        if not p or not p["online"]:
            continue
        h = hosts[n]
        want = [(f, FEATURES[f]["container"]) for f in h["roles"] if f in FEATURES and FEATURES[f]["container"] and state(f, n, h)[0] == "ok"]
        rc, out = ssh(p["ip"], "docker ps --format '{{.Names}}' 2>/dev/null; echo ---; "
                      "journalctl -u fleet-reconcile --no-pager -n 400 2>/dev/null | grep 'PLAY RECAP' -A1 | tail -1 | grep -o -E 'failed=[0-9]+' ; "
                      "docker logs --tail 3 consigliere-reconcile 2>&1 | grep -o -E 'run (finished OK|FAILED)' | tail -1")
        if rc != 0:
            print(f"  {n:12} cannot check ({out.splitlines()[-1][:70] if out else 'ssh failed'})")
            continue
        running, _, tail = out.partition("---")
        names = set(running.split())
        miss = [c for f, c in want if c not in names]
        rec = tail.strip().replace("\n", " ") or "no reconcile result found"
        print(f"  {n:12} {'all declared containers running' if not miss else 'NOT RUNNING: ' + ', '.join(miss)}; last reconcile: {rec}")
    return 0


def cmd_onboard(hosts, name, typ, docker, write):
    n = name.lower()
    if n in hosts:
        print(f"{n} is already in hosts.yml. See:  scripts/audit.sh node {n}")
        return 2
    typ = typ or "lxc"
    lines = [f"    {n}:", f"      type: {typ}", "      # site: ?                  # home | office | ..."]
    util = ["docker"] if docker else []
    if util:
        lines.append(f"      util: [{', '.join(util)}]")
    feats = []
    for s in standards():
        if s["feature"] == "arkeep_agent":
            feats.append("arkeep")
    if feats:
        lines.append(f"      feat: [{', '.join(feats)}]")
    if any(s["feature"] == "beszel_agent" for s in standards()):
        if secret_exists("beszel.agent"):
            lines.append("      prop: [beszel]")
        else:   # a host with this tag fails its run until the shared secret exists, so it starts commented out
            lines.append("      # prop: [beszel]            # enable after: scripts/secrets.sh create beszel.agent")
    block = "\n".join(lines)
    print(f"Entry for config/inventory/hosts.yml (the key must equal the node's Tailscale hostname, lowercase):\n\n{block}\n")
    if write:
        with open(A.HOSTS, "a") as fh:
            fh.write("\n" + block + "\n")
        print("Appended to config/inventory/hosts.yml.\n")
    steps = [
        f"On the node: set its hostname to {n}  (hostnamectl set-hostname {n}); for an LXC also enable /dev/net/tun (see runbooks/adding-a-node.md).",
        f"Join the tailnet with a TAGGED, one-off auth key; the node must show as {n} in the Tailscale admin console.",
        "Commit and push the entry above (scripts/preflight.sh --strict first).",
        "On the node run bootstrap.sh (it detects Debian/Ubuntu, Unraid or macOS by itself), as in runbooks/adding-a-node.md.",
        f"When it prints the age key:  scripts/access.sh add-host {n} <key>  &&  scripts/access.sh sync, then commit and push, and press Enter on the node.",
    ]
    if docker:
        steps.append(f"Arcane: add an edge agent for {n} in the manager, then put arcane_agent_token in config/vars/host/{n}.yml (or set arcane_agent_skip: true).")
    steps.append("Check it:  scripts/audit.sh node " + n + "   and   scripts/audit.sh live --ssh")
    for i, s in enumerate(steps, 1):
        print(f"{i}. {s}")
    return 0


def main(argv):
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    hosts, *_ = declared()
    cmd = argv[0] if argv else "matrix"
    rest = argv[1:]
    if cmd == "matrix":
        cmd_matrix(hosts)
        return 0
    if cmd == "missing" and rest:
        return cmd_missing(hosts, rest[0])
    if cmd == "node" and rest:
        return cmd_node(hosts, rest[0])
    if cmd == "live":
        return cmd_live(hosts, "--ssh" in rest)
    if cmd == "onboard" and rest:
        typ = rest[rest.index("--type") + 1] if "--type" in rest else None
        return cmd_onboard(hosts, rest[0], typ, "--docker" in rest, "--write" in rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
