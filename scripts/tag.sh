#!/usr/bin/env bash
# Add or remove a tag value on hosts (see scripts/tag_hosts.py).
exec python3 "$(dirname "$0")/tag_hosts.py" "$@"
