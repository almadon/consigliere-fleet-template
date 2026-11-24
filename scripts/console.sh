#!/usr/bin/env bash
# Fleet console (Muximux). Usage: scripts/console.sh init [--host <host>]   (see scripts/console_init.py)
case "${1:-}" in
  init) shift; exec python3 "$(dirname "$0")/console_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/console_init.py" --help ;;
esac
