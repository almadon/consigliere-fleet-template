#!/usr/bin/env bash
# Safety checks for this fleet repo.
#   scripts/preflight.sh            fatal: any secret that isn't sops-encrypted;
#                                   warns about leftover CHANGEME placeholders
#   scripts/preflight.sh --strict   placeholders are fatal too (run before deploying)
# The pre-commit hook (.githooks/pre-commit) runs the default mode.
set -euo pipefail
cd "$(dirname "$0")/.."
strict=0; [ "${1:-}" = "--strict" ] && strict=1
rc=0

# Every secret must be sops-encrypted (never plaintext, never a legacy ansible-vault file).
while IFS= read -r f; do
  header="$(head -1 "$f")"
  if printf '%s' "$header" | grep -q '^\$ANSIBLE_VAULT;'; then
    # Still encrypted, so safe to commit, but hosts can only read sops files.
    level=WARN; [ "$strict" = 1 ] && level=ERROR
    echo "$level: $f is a legacy ansible-vault file -- run: scripts/secrets.sh migrate <scope>" >&2
    [ "$strict" = 1 ] && rc=1
  elif ! grep -q '^sops:' "$f"; then
    echo "ERROR: $f is not sops-encrypted -- run: scripts/secrets.sh encrypt <scope>" >&2
    rc=1
  fi
done < <(find config/secrets -type f -name '*.yml' 2>/dev/null)

# .sops.yaml is generated; flag it when it no longer matches access.yml + the host table.
if [ -x scripts/access.sh ] && [ -f config/access.yml ]; then
  if ! scripts/access.sh sync --check >/dev/null 2>&1; then
    level=WARN; [ "$strict" = 1 ] && level=ERROR
    echo "$level: .sops.yaml is out of date (or the framework checkout was not found) -- run: scripts/access.sh sync" >&2
    [ "$strict" = 1 ] && rc=1
  fi
fi

left="$(grep -rnE 'CHANGE-?ME' config --include='*.yml' --exclude='*.example' --exclude-dir=secrets || true)"
if [ -n "$left" ]; then
  echo "Placeholders still to fill in:" >&2
  echo "$left" >&2
  [ "$strict" = 1 ] && rc=1
fi
exit $rc
