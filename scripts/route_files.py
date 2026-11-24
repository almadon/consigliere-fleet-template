"""The fleet's per-domain route files (config/routes/<domain>.yml), read with the framework's own parser so the scripts and the reconciler cannot disagree.

The parser is hosts/plugins/lookup/fleet_routes.py in the framework repo. It is found in $CONSIGLIERE_FRAMEWORK, or in a checkout next to this one
(../consigliere). With no config/routes directory there is nothing to read and the framework is not needed.
"""
import importlib.util
import os
import sys

import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ROUTES_DIR = os.path.join(ROOT, "config", "routes")


def _parser():
    for base in (os.environ.get("CONSIGLIERE_FRAMEWORK"), os.path.join(ROOT, "..", "consigliere")):
        if not base:
            continue
        p = os.path.join(base, "hosts", "plugins", "lookup", "fleet_routes.py")
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location("fleet_routes", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def load():
    """(zones, problems): every domain file, validated. Zones are the parser's dicts: name, cert, routes [{route, via}], path."""
    if not os.path.isdir(ROUTES_DIR):
        return [], []
    mod = _parser()
    if mod is None:
        sys.exit("ERROR: config/routes exists but the framework's route parser was not found. Check out the framework next to this repo (../consigliere) or set CONSIGLIERE_FRAMEWORK.")
    return mod.load_zones([ROUTES_DIR], yaml.safe_load)


def for_host(zones, host):
    """[{name, cert, routes}] for the zones with at least one route served by `host`, plus per-host problems (a name used twice)."""
    mod = _parser()
    return mod.routes_for_host(zones, host) if mod else ([], [])
