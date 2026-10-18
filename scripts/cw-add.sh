#!/usr/bin/env bash
# Store a Cert Warden certificate's API keys as an encrypted secret, after checking they work.
#   scripts/cw-add.sh <certificate-name> [cert-warden-url]
# e.g. scripts/cw-add.sh a64.one http://100.100.1.10:4050
#      scripts/cw-add.sh rmrg.casa http://100.120.20.45:4050
# The name must match the certificate's name in Cert Warden exactly. You are asked for the
# certificate's API key and its private key's API key (hidden input); nothing is printed or kept
# in your shell history. The keys are tested with a real download first (HTTP 200 expected), then
# written to config/secrets/cw/<name>.yml, encrypted for the hosts that have cert: [<name>].
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?usage: scripts/cw-add.sh <certificate-name> [cert-warden-url]}"
url="${2:-http://100.100.1.10:4050}"
file="config/secrets/cw/$name.yml"
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
[ ! -e "$file" ] || { echo "ERROR: $file already exists (edit it with: scripts/secrets.sh edit cw.$name)" >&2; exit 1; }

read -rsp "API key of the CERTIFICATE '$name' (Certificates > $name > API Key): " ckey; echo
read -rsp "API key of its PRIVATE KEY (Private Keys > the key used by $name > API Key): " kkey; echo
[ -n "$ckey" ] && [ -n "$kkey" ] || { echo "ERROR: both keys are needed" >&2; exit 1; }

code=$(printf 'header = "X-API-Key: %s.%s"\n' "$ckey" "$kkey" |
  curl -s -K - -o /dev/null -m 15 -w '%{http_code}' "$url/certwarden/api/v1/download/privatecertchains/$name" || true)
case "$code" in
  200) echo "Cert Warden accepted the keys (HTTP 200)." ;;
  401) echo "ERROR: HTTP 401: the certificate exists but those keys are wrong (are the two swapped, or the API key not saved in Cert Warden?)." >&2; exit 1 ;;
  404) echo "ERROR: HTTP 404: Cert Warden has no certificate named '$name' at $url (names are case-sensitive)." >&2; exit 1 ;;
  *)   echo "ERROR: unexpected answer (HTTP $code) from $url." >&2; exit 1 ;;
esac

scripts/access.sh sync --no-update >/dev/null     # makes sure an encryption rule exists for this file
mkdir -p config/secrets/cw
tmp="$file.new"; trap 'rm -f "$tmp"' EXIT
( umask 077; printf -- '---\ncert: "%s"\nkey: "%s"\n' "$ckey" "$kkey" > "$tmp" )
sops --encrypt --in-place --filename-override "$file" "$tmp"
mv "$tmp" "$file"
unset ckey kkey
echo "Created $file. Next: give the hosts cert: [$name] in config/inventory/hosts.yml, run scripts/access.sh sync, commit and push."
