#!/usr/bin/env bash
# Publish a service behind Traefik (see scripts/publish.py).
exec python3 "$(dirname "$0")/publish.py" "$@"
