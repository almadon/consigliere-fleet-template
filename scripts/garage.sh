#!/usr/bin/env bash
# Garage (S3 object store). Usage: scripts/garage.sh init|webui [--host <host>]  (see scripts/garage_init.py)
case "${1:-}" in
  init|webui) exec python3 "$(dirname "$0")/garage_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/garage_init.py" --help ;;
esac
