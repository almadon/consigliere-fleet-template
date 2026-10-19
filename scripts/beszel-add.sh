#!/usr/bin/env bash
# Roll the Beszel agent out to the fleet (see scripts/beszel_add.py).
exec python3 "$(dirname "$0")/beszel_add.py" "$@"
