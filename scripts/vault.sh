#!/usr/bin/env bash
# Create/edit/view the vault file for one secret SCOPE, with the right vault id
# and path, so you never hand-type them.
#
#   scripts/vault.sh create <scope>   encrypt vault.yml.example into place (placeholders)
#   scripts/vault.sh edit   <scope>
#   scripts/vault.sh view   <scope>
#
# <scope> is one of:
#   base             config/vars/group/all/vault.yml
#   <group>          config/vars/group/<group>/vault.yml   (every host in the group)
#   <kind>.<name>    config/secrets/<kind>/<name>.yml      (only hosts that request it)
#                    e.g. cw._a64.one = Cert Warden API keys for certificate _a64.one
# The scope is also the vault id, and the name of the password file hosts are given. Your password for a scope is
# read from $VAULT_PASSWORDS_DIR/<scope> (default ~/.config/consigliere/vault/)
# if that file exists, otherwise you are prompted.
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-}"; scope="${2:-}"
[ -n "$cmd" ] && [ -n "$scope" ] || { sed -n 2,20p "$0" | sed 's/^# \{0,1\}//'; exit 2; }

case "$scope" in
  base) dir=config/vars/group/all; file="$dir/vault.yml"; example="$dir/vault.yml.example" ;;
  *.*)  kind="${scope%%.*}"; dir="config/secrets/$kind"; file="$dir/${scope#*.}.yml"
        example="$dir/_template.yml.example" ;;
  *)    dir="config/vars/group/$scope"; file="$dir/vault.yml"; example="$dir/vault.yml.example" ;;
esac
pwfile="${VAULT_PASSWORDS_DIR:-$HOME/.config/consigliere/vault}/$scope"
if [ -f "$pwfile" ]; then idsrc="$scope@$pwfile"; else idsrc="$scope@prompt"; fi

case "$cmd" in
  create)
    [ ! -e "$file" ] || { echo "ERROR: $file already exists (use edit)" >&2; exit 1; }
    [ -f "$example" ] || { echo "ERROR: no $example to start from" >&2; exit 1; }
    mkdir -p "$dir"
    # Encrypt a temporary copy and move it into place only on success, so a
    # cancelled password prompt never leaves a plaintext file behind.
    tmp="$file.new"; trap 'rm -f "$tmp"' EXIT
    cp "$example" "$tmp"
    ansible-vault encrypt --encrypt-vault-id "$scope" --vault-id "$idsrc" "$tmp"
    mv "$tmp" "$file"
    echo "Created $file (placeholders). Now: scripts/vault.sh edit $scope"
    ;;
  edit) ansible-vault edit --encrypt-vault-id "$scope" --vault-id "$idsrc" "$file" ;;
  view) ansible-vault view --vault-id "$idsrc" "$file" ;;
  *) echo "ERROR: unknown command $cmd" >&2; exit 2 ;;
esac
