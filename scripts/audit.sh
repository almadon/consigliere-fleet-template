#!/usr/bin/env bash
# What each node has and is missing: see scripts/audit.py (or run with no arguments).
# Needs a python3 with PyYAML and Ansible's libraries: the one that runs ansible.
here="$(dirname "$0")"
py="${ACCESS_PYTHON:-python3}"
if ! "$py" -c 'import yaml, ansible' 2>/dev/null; then
  shebang="$(head -1 "$(command -v ansible 2>/dev/null)" 2>/dev/null | sed -n 's/^#! *//p')"
  [ -n "$shebang" ] && py="$shebang"
fi
exec "$py" "$here/audit.py" "$@"
