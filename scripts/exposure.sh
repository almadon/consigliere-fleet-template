#!/usr/bin/env bash
# Exposure watch (open ports on the fleet's public addresses). Usage: scripts/exposure.sh init|key|learn|check|run [--host <host>]  (see scripts/exposure_init.py)
exec python3 "$(dirname "$0")/exposure_init.py" "$@"
