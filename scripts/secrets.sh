#!/usr/bin/env bash
# Create/edit/view secrets: sops-encrypted files, one per scope <kind>.<name>
# (config/secrets/<kind>/<name>.yml), readable only by the hosts granted to it.
#
#   scripts/secrets.sh init-admin [name]  make your admin age key (once) and register it
#   scripts/secrets.sh create  <scope>    new file from its .example, encrypted
#   scripts/secrets.sh edit    <scope>    edit in nano (SECRETS_EDITOR=... to change)
#   scripts/secrets.sh view    <scope>
#   scripts/secrets.sh decrypt <scope>    decrypt IN PLACE to edit in an IDE (preflight refuses to commit it)
#   scripts/secrets.sh encrypt <scope>    encrypt a decrypted file again
#   scripts/secrets.sh rotate  <scope>    new data key, re-encrypt (do after removing a reader)
#   scripts/secrets.sh migrate <scope>    convert an old ansible-vault file to sops
#
# e.g. arkeep.agent, arkeep.server, cw._a64.one. Who can read each is derived from
# the host table and tag manifests: see scripts/access.sh. Your private key is
# $SOPS_AGE_KEY_FILE (default ~/.config/sops/age/keys.txt).
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-}"; scope="${2:-}"
[ -n "$cmd" ] || { sed -n 2,16p "$0" | sed 's/^# \{0,1\}//'; exit 2; }
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
export EDITOR="${SECRETS_EDITOR:-nano}"

if [ "$cmd" = init-admin ]; then
  name="${2:-$(whoami)}"
  command -v age-keygen >/dev/null || { echo "ERROR: age-keygen not found (brew install age / apt install age)" >&2; exit 1; }
  if [ ! -f "$SOPS_AGE_KEY_FILE" ]; then
    mkdir -p "$(dirname "$SOPS_AGE_KEY_FILE")"; chmod 700 "$(dirname "$SOPS_AGE_KEY_FILE")"
    ( umask 077; age-keygen -o "$SOPS_AGE_KEY_FILE" 2>/dev/null )
    echo "Created your admin key: $SOPS_AGE_KEY_FILE (back it up; without it, and any other admin key, secrets are lost)"
  fi
  scripts/access.sh add-admin "$name" "$(age-keygen -y "$SOPS_AGE_KEY_FILE")"
  exit 0
fi

[ -n "$scope" ] || { echo "ERROR: $cmd needs a scope, e.g. arkeep.agent" >&2; exit 2; }
case "$scope" in *.*) ;; *) echo "ERROR: scope must look like <kind>.<name> (e.g. arkeep.agent)" >&2; exit 2 ;; esac
kind="${scope%%.*}"; name="${scope#*.}"
dir="config/secrets/$kind"; file="$dir/$name.yml"
example="$dir/$name.yml.example"; [ -f "$example" ] || example="$dir/_template.yml.example"

is_sops() { grep -q '^sops:' "$1"; }
need_file() { [ -f "$file" ] || { echo "ERROR: $file does not exist (scripts/secrets.sh create $scope)" >&2; exit 1; }; }

case "$cmd" in
  create)
    [ ! -e "$file" ] || { echo "ERROR: $file already exists (use edit)" >&2; exit 1; }
    [ -f "$example" ] || { echo "ERROR: no $example to start from" >&2; exit 1; }
    scripts/access.sh sync --no-update >/dev/null     # make sure a rule exists for this file
    mkdir -p "$dir"
    # Encrypt a temporary copy and move it into place only on success, so a failure
    # never leaves a plaintext file behind.
    tmp="$file.new"; trap 'rm -f "$tmp"' EXIT
    cp "$example" "$tmp"
    sops --encrypt --in-place --filename-override "$file" "$tmp"
    mv "$tmp" "$file"
    echo "Created $file (placeholders). Now: scripts/secrets.sh edit $scope"
    ;;
  edit)    need_file; sops "$file" ;;
  view)    need_file; sops --decrypt "$file" ;;
  decrypt)
    need_file; is_sops "$file" || { echo "$file is already decrypted" >&2; exit 1; }
    sops --decrypt --in-place "$file"
    echo "Decrypted $file IN PLACE. Edit it, then: scripts/secrets.sh encrypt $scope"
    ;;
  encrypt)
    need_file; ! is_sops "$file" || { echo "$file is already encrypted" >&2; exit 1; }
    scripts/access.sh sync --no-update >/dev/null
    sops --encrypt --in-place "$file"
    ;;
  rotate)  need_file; sops rotate --in-place "$file" ;;
  migrate)
    need_file
    head -1 "$file" | grep -q '^\$ANSIBLE_VAULT;' || { echo "ERROR: $file is not an ansible-vault file" >&2; exit 1; }
    scripts/access.sh sync --no-update >/dev/null
    tmp="$file.new"; trap 'rm -f "$tmp"' EXIT
    old="$scope@prompt"; [ -z "${OLD_VAULT_PASSWORD_FILE:-}" ] || old="$scope@$OLD_VAULT_PASSWORD_FILE"
    ( umask 077; ansible-vault view --vault-id "$old" "$file" > "$tmp" )
    sops --encrypt --in-place --filename-override "$file" "$tmp"
    mv "$tmp" "$file"
    echo "Migrated $file to sops."
    ;;
  *) echo "ERROR: unknown command $cmd" >&2; exit 2 ;;
esac
