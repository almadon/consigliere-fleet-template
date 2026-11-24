#!/usr/bin/env python3
"""Publish a service: add a Traefik route on the right proxy host (and optionally a console tile).

  scripts/publish.sh [--host <host>] [--name wiki] [--domain wiki.example.com] [--backend http://myhost:3000]
                     [--profile app|strict|relaxed|framed|none] [--tile "Group"]

Anything not given on the command line is asked for. It appends one line to the domain's route file, config/routes/<domain>.yml (created if missing; the domain is
the one named after the certificate that covers the name, for example example.com or ctrl.example.com), with `via: <host>` when the host is not the file's default,
appends a tile to config/vars/group/util_muximux.yml
when you give a tile group, then runs the fleet preflight and shows the diff. Nothing is committed or pushed.
Reminders it prints: the DNS record (point it at the proxy host), and the certificate that must cover the domain.
"""
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOSTS = os.path.join(ROOT, "config", "inventory", "hosts.yml")
CONSOLE = os.path.join(ROOT, "config", "vars", "group", "util_muximux.yml")
PROFILES = ["app", "strict", "relaxed", "framed", "none"]


def die(msg):
    sys.exit(f"ERROR: {msg}")


def opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def ask(prompt, default=None):
    v = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default


def proxy_hosts():
    """Hosts whose inventory entry has traefik in util."""
    out, cur = [], None
    for ln in open(HOSTS).read().split("\n"):
        m = re.match(r"^    ([A-Za-z0-9_.-]+):\s*(#.*)?$", ln)
        if m:
            cur = m.group(1).lower()
        m = re.match(r"^      util:\s*\[(.*?)\]", ln)
        if m and cur and "traefik" in [x.strip() for x in m.group(1).split(",")]:
            out.append(cur)
    return out


def append_to_list(path, key, line):
    """Insert `line` after the last entry of the top-level list `key:` in the file."""
    lines = open(path).read().split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^{re.escape(key)}:\s*(#.*)?$", ln)), None)
    if start is None:
        die(f"{os.path.relpath(path, ROOT)} has no '{key}:' list")
    end, last = len(lines), start
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln.strip() and not ln.startswith((" ", "#")):
            end = i
            break
        if ln.strip() and not ln.lstrip().startswith("#"):
            last = i
    lines.insert(last + 1, line)
    open(path, "w").write("\n".join(lines))


def zone_for(domain):
    """(zone, cert) for a domain name: the longest cert: name in the host table that the name ends with, else its last two labels."""
    certs = set()
    for m in re.finditer(r"^\s+cert:\s*\[(.*?)\]", open(HOSTS).read(), re.M):
        certs |= {x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()}
    for c in sorted(certs, key=len, reverse=True):
        if domain == c or domain.endswith("." + c):
            return c, c
    return ".".join(domain.split(".")[-2:]), None


def all_domains():
    found = set()
    for f in glob.glob(os.path.join(ROOT, "config", "vars", "**", "*.yml"), recursive=True) + glob.glob(os.path.join(ROOT, "config", "routes", "*.yml")):
        for m in re.finditer(r"host:\s*\[?\s*([A-Za-z0-9._,\s-]+?)\s*[\]},\n]", open(f).read()):
            found.update(x.strip().lower() for x in m.group(1).split(","))
    return found


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    hosts = proxy_hosts()
    if not hosts:
        die("no host has util: [traefik] in config/inventory/hosts.yml")
    print("Proxy hosts (they run Traefik): " + ", ".join(hosts))
    host = (opt(argv, "--host") or ask("Which proxy host serves it", hosts[0])).lower()
    if host not in hosts:
        die(f"'{host}' does not run Traefik (util: [traefik])")
    domain = (opt(argv, "--domain") or ask("Public domain (e.g. wiki.example.com)") or "").lower()
    if not re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$", domain or ""):
        die("that does not look like a domain name")
    if domain in all_domains():
        die(f"{domain} is already routed somewhere in config/routes or config/vars (search for it before adding another route)")
    backend = opt(argv, "--backend") or ask("Backend (http://container:port on the proxy host's networks, or http://100.x.y.z:port)")
    if not re.match(r"^https?://[A-Za-z0-9._-]+(:\d+)?(/.*)?$", backend or ""):
        die("the backend must look like http://name-or-ip:port")
    profile = opt(argv, "--profile") or ask(f"Security profile ({'/'.join(PROFILES)}; app is the safe default)", "app")
    if profile not in PROFILES:
        die(f"profile must be one of {', '.join(PROFILES)}")
    name = opt(argv, "--name") or ask("Short route name", domain.split(".")[0])
    if not re.match(r"^[a-z0-9-]+$", name or ""):
        die("the route name may use lowercase letters, digits and hyphens only")
    tile = opt(argv, "--tile")
    if tile is None and sys.stdin.isatty():
        tile = ask("Add a console tile? Group name, or empty for none", "") or None

    zone, cert = zone_for(domain)
    path = os.path.join(ROOT, "config", "routes", f"{zone}.yml")
    default_via = None
    if os.path.exists(path):
        m = re.search(r"^via:\s*([A-Za-z0-9_.-]+)\s*(#.*)?$", open(path).read(), re.M)
        default_via = m.group(1).lower() if m else None
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(f"---\n# Routes for {zone}: which host's Traefik serves each one is `via` (this file's default, or the route's own).\n"
                              + (f"cert: {cert}\n" if cert else "") + f"via: {host}\nroutes:\n")
        default_via = host
    prof = "" if profile == "app" else f", profile: {profile}"
    via = "" if default_via == host else f", via: {host}"
    append_to_list(path, "routes", f"  - {{name: {name}, host: {domain}, backend: \"{backend}\"{prof}{via}}}")
    print(f"Added route {domain} -> {backend} to config/routes/{zone}.yml" + (f" (via {host})" if via else ""))
    if tile:
        title = name.replace("-", " ").title()
        append_to_list(CONSOLE, "muximux_apps", f"  - {{name: {title}, url: \"https://{domain}\", group: {tile}}}")
        print(f"Added console tile '{title}' (group {tile}; the group must exist in muximux_groups)")

    p = subprocess.run([os.path.join(ROOT, "scripts", "preflight.sh"), "--strict"], cwd=ROOT, capture_output=True, text=True)
    print("Preflight:", "ok" if p.returncode == 0 else "FAILED\n" + (p.stdout + p.stderr)[-600:])
    subprocess.run(["git", "diff", "--stat"], cwd=ROOT)
    print(f"\nStill to do:\n  - DNS: an A record for {domain}"
          f" (skip it if a wildcard record already points at {host})\n  - {host} must serve a certificate that covers {domain}" + (f" ({cert}: put it in its cert: list)" if cert else " (none of the certificates in the host table matches this name)"))
    print("Review it, then:  git add -A && git commit -m 'publish " + domain + "' && git push")
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
