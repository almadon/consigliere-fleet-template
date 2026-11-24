#!/usr/bin/env bash
# Second Proxmox Backup Server that pulls a primary PBS. Usage: scripts/pbs.sh init [--host <host>]  (see scripts/pbs_init.py)
case "${1:-}" in
  init) exec python3 "$(dirname "$0")/pbs_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/pbs_init.py" --help ;;
esac
