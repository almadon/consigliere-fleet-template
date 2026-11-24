#!/usr/bin/env bash
# The fleet's notification service (Apprise API). Usage: scripts/apprise.sh init [--host <host>]   (see scripts/apprise_init.py)
case "${1:-}" in
  init) shift; exec python3 "$(dirname "$0")/apprise_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/apprise_init.py" --help ;;
esac
