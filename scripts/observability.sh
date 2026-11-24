#!/usr/bin/env bash
# Loki + Grafana. Usage: scripts/observability.sh init [--host <host>]  (see scripts/observability_init.py)
case "${1:-}" in
  init) shift; exec python3 "$(dirname "$0")/observability_init.py" "$@" ;;
  *) exec python3 "$(dirname "$0")/observability_init.py" --help ;;
esac
