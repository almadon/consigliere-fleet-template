#!/usr/bin/env bash
# Create/edit/view the vault file for one secret SCOPE, with the right vault id
# and path, so you never hand-type them.
#
#   scripts/vault.sh create <scope>   encrypt vault.yml.example into place (placeholders)
#   scripts/vault.sh edit   <scope>
#   scripts/vault.sh view   <scope>
#
# <scope> is `base` (config/vars/group/all/vault.yml) or a group name
# (config/vars/group/<group>/vault.yml). The scope is also the vault id, and
# the name of the password file hosts are given. Your password for a scope is
# read from $VAULT_PASSWORDS_DIR/<scope> (default ~/.config/consigliere/vault/)
# if that file exists, otherwise you are prompted.
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-}"; scope="${2:-}"
[ -n "$cmd" ] && [ -n "$scope" ] || { sed -n 2,16p "$0" | sed 's/^# \{0,1\}//'; exit 2; }

dir="config/vars/group/$([ "$scope" = base ] && echo all || echo "$scope")"
file="$dir/vault.yml"
pwfile="${VAULT_PASSWORDS_DIR:-$HOME/.config/consigliere/vault}/$scope"
if [ -f "$pwfile" ]; then idsrc="$scope@$pwfile"; else idsrc="$scope@prompt"; fi

case "$cmd" in
  create)
    [ ! -e "$file" ] || { echo "ERROR: $file already exists (use edit)" >&2; exit 1; }
    [ -f "$dir/vault.yml.example" ] || { echo "ERROR: no $dir/vault.yml.example to start from" >&2; exit 1; }
    cp "$dir/vault.yml.example" "$file"
    ansible-vault encrypt --encrypt-vault-id "$scope" --vault-id "$idsrc" "$file"
    echo "Created $file (placeholders). Now: scripts/vault.sh edit $scope"
    ;;
  edit) ansible-vault edit --encrypt-vault-id "$scope" --vault-id "$idsrc" "$file" ;;
  view) ansible-vault view --vault-id "$idsrc" "$file" ;;
  *) echo "ERROR: unknown command $cmd" >&2; exit 2 ;;
esac
