#!/usr/bin/env bash
# Run reporting through Pushover. Usage: scripts/notify.sh init [--hosts <host>|all|a,b] [--replace]  (see scripts/notify_init.py)
case "${1:-}" in
  init) shift; exec python3 "$(dirname "$0")/notify_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/notify_init.py" --help ;;
esac
