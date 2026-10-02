#!/usr/bin/env bash
# Safety checks for this fleet repo.
#   scripts/preflight.sh            fatal: any vault file that isn't encrypted;
#                                   warns about leftover CHANGEME placeholders
#   scripts/preflight.sh --strict   placeholders are fatal too (run before deploying)
# The pre-commit hook (.githooks/pre-commit) runs the default mode.
set -euo pipefail
cd "$(dirname "$0")/.."
strict=0; [ "${1:-}" = "--strict" ] && strict=1
rc=0

while IFS= read -r f; do
  if ! head -1 "$f" | grep -q '^\$ANSIBLE_VAULT;'; then
    echo "ERROR: $f is not ansible-vault encrypted -- run: ansible-vault encrypt $f" >&2
    rc=1
  fi
done < <(find config -type f -name 'vault*.yml')

left="$(grep -rnE 'CHANGE-?ME' config --include='*.yml' --exclude='*.example' --exclude='vault*.yml' || true)"
if [ -n "$left" ]; then
  echo "Placeholders still to fill in:" >&2
  echo "$left" >&2
  [ "$strict" = 1 ] && rc=1
fi
exit $rc
