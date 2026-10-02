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
  header="$(head -1 "$f")"
  if ! printf '%s' "$header" | grep -q '^\$ANSIBLE_VAULT;'; then
    echo "ERROR: $f is not ansible-vault encrypted -- run: scripts/vault.sh create <scope>" >&2
    rc=1
    continue
  fi
  # The vault id must match the folder (all -> base): that is what lets a host
  # be given only the passwords for the scopes it should read.
  dir="$(basename "$(dirname "$f")")"
  want="$([ "$dir" = all ] && echo base || echo "$dir")"
  have="$(printf '%s' "$header" | cut -d';' -f4)"
  if [ "$have" != "$want" ]; then
    level=WARN; [ "$strict" = 1 ] && level=ERROR
    echo "$level: $f has vault id '${have:-<none>}', expected '$want' (re-encrypt: ansible-vault rekey --new-vault-id $want@prompt $f)" >&2
    [ "$strict" = 1 ] && rc=1
  fi
done < <(find config -type f -name 'vault*.yml')

left="$(grep -rnE 'CHANGE-?ME' config --include='*.yml' --exclude='*.example' --exclude='vault*.yml' || true)"
if [ -n "$left" ]; then
  echo "Placeholders still to fill in:" >&2
  echo "$left" >&2
  [ "$strict" = 1 ] && rc=1
fi
exit $rc
