#!/usr/bin/env python3
"""Catch conflicting Traefik routes BEFORE they are pushed (the role refuses them on the host too).

For every host with util: [traefik], gathers the routes it serves from two places, merged: the traefik_server_routes* variables it would see (group files for
each of its table values, the 'all' group, its host file and its routes file), and the per-domain route files (config/routes/<domain>.yml, each route's `via`
naming the host that serves it), and checks:
  - route names are unique and look like a-z, 0-9, dashes            (error)
  - no two routes match the same request (same host, or same rule)    (error)
  - a route file is valid, every `via` names a host that exists and runs Traefik, and each host serves the certificate its files name   (error)
  - the same domain is routed on more than one host                   (warning: fine while moving a service)
Exit 1 on errors. Run by scripts/preflight.sh.
"""
import glob
import os
import re
import sys

import yaml

import route_files

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
V = os.path.join(ROOT, "config", "vars")
DIMS = ("type", "org", "site", "util", "feat", "cert", "prop", "fw")


def load(path):
    try:
        return yaml.safe_load(open(path)) or {}
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {os.path.relpath(path, ROOT)} is not valid YAML: {e}", file=sys.stderr)
        sys.exit(1)


def files_for(host, tags):
    out = [os.path.join(V, "group", "all.yml")]
    for dim in DIMS:
        for val in tags.get(dim) or []:
            out.append(os.path.join(V, "group", f"{dim}_{re.sub('[^A-Za-z0-9_]', '_', str(val))}.yml"))
    out.append(os.path.join(V, "host", f"{host}.yml"))
    out += [os.path.join(V, "routes", f"{host}.yml")] + sorted(glob.glob(os.path.join(V, "routes", host, "*.yml")))
    return [f for f in out if os.path.exists(f)]


def cert_names(host, tags):
    """Certificate names the host's vars say it fetches besides its cert: tags (certwarden_agent_certs*: plain names or {name: ...})."""
    out = set(tags.get("cert") or [])
    for f in files_for(host, tags):
        for var, val in load(f).items():
            if re.match(r"^certwarden_agent_certs(_.*)?$", var) and isinstance(val, list):
                out |= {(x.get("name") if isinstance(x, dict) else x) for x in val}
    return out


def host_routes(host, tags, zones):
    """[(source file, route)] this host serves, from the vars layers and from the per-domain files, plus the zones it takes routes from."""
    out = []
    for f in files_for(host, tags):
        rel = os.path.relpath(f, ROOT)
        for var, val in load(f).items():
            if not re.match(r"^traefik_server_routes(_.*)?$", var) or not isinstance(val, list):
                continue
            out += [(rel, r) for r in val if isinstance(r, dict)]
    mine, _ = route_files.for_host(zones, host)
    for z in mine:
        out += [(f"config/routes/{z['name']}.yml", r) for r in z["routes"]]
    return out, mine


def keys_of(route):
    if route.get("rule"):
        return [str(route["rule"]).strip()]
    hosts = route.get("host")
    hosts = [hosts] if isinstance(hosts, str) else (hosts or [])
    return [f"Host(`{h.lower()}`)" for h in hosts]


def show(only=None):
    """Print every route each proxy host serves, and the file it is defined in."""
    table = load(os.path.join(ROOT, "config", "inventory", "hosts.yml")).get("all", {}).get("hosts", {}) or {}
    for host, tags in table.items():
        tags = tags or {}
        host = host.lower()
        if "traefik" not in (tags.get("util") or []) or (only and host != only):
            continue
        rows = []
        zones, _ = route_files.load()
        for rel, r in host_routes(host, tags, zones)[0]:
            hosts = r.get("host")
            hosts = [hosts] if isinstance(hosts, str) else (hosts or [])
            dest = r.get("backend") or ("redirect -> " + str((r.get("redirect") or {}).get("to"))) or "?"
            if r.get("root"):
                dest = "static " + str(r["root"])
            rows.append((", ".join(hosts) or str(r.get("rule")), dest, r.get("profile", "app"), r.get("name", "?"), rel))
        print(f"\n{host}  ({len(rows)} routes)")
        for h, d, p, n, rel in sorted(rows):
            print(f"  {h:42} {d:40} {p:8} {n:12} {rel}")
    return 0


def main():
    if "--show" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        return show(args[0].lower() if args else None)
    table = load(os.path.join(ROOT, "config", "inventory", "hosts.yml")).get("all", {}).get("hosts", {}) or {}
    errors, warns, domains = [], [], {}
    zones, problems = route_files.load()
    errors += problems
    lower = {h.lower(): (t or {}) for h, t in table.items()}
    for z in zones:
        for e in z["routes"]:
            for v in e["via"]:
                if v not in lower:
                    errors.append(f"config/routes/{z['name']}.yml: route {e['route']['name']} has via {v}, which is not in the host table")
                elif "traefik" not in (lower[v].get("util") or []):
                    errors.append(f"config/routes/{z['name']}.yml: route {e['route']['name']} has via {v}, which does not run Traefik (util: [traefik])")
    for host, tags in table.items():
        tags = tags or {}
        if "traefik" not in (tags.get("util") or []):
            continue
        host = host.lower()
        seen_names, seen_keys = {}, {}
        entries, mine = host_routes(host, tags, zones)
        errors += [f"{host}: {x}" for x in route_files.for_host(zones, host)[1]]
        have = cert_names(host, tags)
        for z in mine:
            if z["cert"] and z["cert"] not in have:
                errors.append(f"{host}: config/routes/{z['name']}.yml names the certificate {z['cert']}, which this host does not fetch (cert: {sorted(have)})")
        for rel, r in entries:
            n = r.get("name", "")
            if not re.match(r"^[a-z0-9][a-z0-9-]*$", str(n)):
                errors.append(f"{host}: route name '{n}' in {rel} must be lowercase a-z, 0-9, dashes")
            if n in seen_names:
                errors.append(f"{host}: route name '{n}' is defined twice ({seen_names[n]} and {rel})")
            seen_names[n] = rel
            for k in keys_of(r):
                if k in seen_keys:
                    errors.append(f"{host}: two routes match {k}: '{seen_keys[k][0]}' ({seen_keys[k][1]}) and '{n}' ({rel})")
                seen_keys[k] = (n, rel)
                m = re.fullmatch(r"Host\(`(.+)`\)", k)
                if m:
                    domains.setdefault(m.group(1), set()).add(host)
    for d, hs in sorted(domains.items()):
        if len(hs) > 1:
            warns.append(f"{d} is routed on more than one host ({', '.join(sorted(hs))}): fine while moving it, but only one DNS record can point at it")
    for w in warns:
        print("WARN: " + w, file=sys.stderr)
    for e in errors:
        print("ERROR: " + e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
