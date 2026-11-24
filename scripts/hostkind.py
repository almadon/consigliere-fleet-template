"""What kind of reconciler a host runs, from its host-table entry. Shared by reconcile_now.py and fleet_run.py.

A host with the container reconciler (framework hosts/bootstrap/unraid and hosts/bootstrap/alpine) is reconciled by one long-lived container on its Docker
socket, not by systemd, and has no host-level package management of its own to drive. The table says so with `os:` (see the header of
config/inventory/hosts.yml); `type: unraid` is also accepted for a host written before `os:` existed. CONTAINER_OS mirrors the platforms whose profile in the
framework's hosts/platforms/ is reconciled by a container today: change it when another platform moves to a host-run reconciler.
"""

CONTAINER_OS = {"unraid", "alpine"}


def container_reconciled(host):
    host = host or {}
    return str(host.get("type", "")) == "unraid" or str(host.get("os", "")).lower() in CONTAINER_OS
