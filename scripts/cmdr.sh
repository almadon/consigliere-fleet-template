#!/usr/bin/env bash
# cmdr, the fleet's control page. Usage: scripts/cmdr.sh init [--host <host>]   (see scripts/cmdr_init.py)
case "${1:-}" in
  init) shift; exec python3 "$(dirname "$0")/cmdr_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/cmdr_init.py" --help ;;
esac
