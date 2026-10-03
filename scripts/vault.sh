#!/usr/bin/env bash
# Create/edit/view the vault file for one secret SCOPE, with the right vault id
# and path, so you never hand-type them.
#
#   scripts/vault.sh create  <scope>   encrypt the example into place (placeholders)
#   scripts/vault.sh edit    <scope>   edit in nano (VAULT_EDITOR=... to change), re-encrypts on save
#   scripts/vault.sh view    <scope>
#   scripts/vault.sh decrypt <scope>   decrypt IN PLACE, to edit in an IDE
#   scripts/vault.sh encrypt <scope>   encrypt a decrypted file again, with the right id
#
# <scope> is one of:
#   <kind>.<name>    config/secrets/<kind>/<name>.yml   e.g. arkeep.agent, arkeep.server,
#                    cw._example.com (Cert Warden keys for certificate _example.com). Read by
#                    the roles that need it, only on hosts that hold its password.
#   <group>          config/vars/group/<group>/vault.yml   (every host in the group)
#   base             config/vars/group/all/vault.yml       (every host; keep it tiny)
# The scope is also the vault id, and the name of the password file hosts are
# given. Your password for a scope is read from $VAULT_PASSWORDS_DIR/<scope>
# (default ~/.config/consigliere/vault/) if that file exists, otherwise you are
# prompted.
#
# After `decrypt` the secrets are plaintext in the working tree until you run
# `encrypt`; the pre-commit hook (preflight.sh) refuses to commit them.
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-}"; scope="${2:-}"
[ -n "$cmd" ] && [ -n "$scope" ] || { sed -n 2,22p "$0" | sed 's/^# \{0,1\}//'; exit 2; }

case "$scope" in
  base) dir=config/vars/group/all; file="$dir/vault.yml"; example="$dir/vault.yml.example" ;;
  *.*)  kind="${scope%%.*}"; name="${scope#*.}"; dir="config/secrets/$kind"; file="$dir/$name.yml"
        example="$dir/$name.yml.example"; [ -f "$example" ] || example="$dir/_template.yml.example" ;;
  *)    dir="config/vars/group/$scope"; file="$dir/vault.yml"; example="$dir/vault.yml.example" ;;
esac
pwfile="${VAULT_PASSWORDS_DIR:-$HOME/.config/consigliere/vault}/$scope"
if [ -f "$pwfile" ]; then idsrc="$scope@$pwfile"; else idsrc="$scope@prompt"; fi
export EDITOR="${VAULT_EDITOR:-nano}"

is_encrypted() { head -1 "$1" | grep -q '^\$ANSIBLE_VAULT;'; }
need_file() { [ -f "$file" ] || { echo "ERROR: $file does not exist (scripts/vault.sh create $scope)" >&2; exit 1; }; }

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
  edit)    need_file; ansible-vault edit --encrypt-vault-id "$scope" --vault-id "$idsrc" "$file" ;;
  view)    need_file; ansible-vault view --vault-id "$idsrc" "$file" ;;
  decrypt)
    need_file
    is_encrypted "$file" || { echo "$file is already decrypted" >&2; exit 1; }
    ansible-vault decrypt --vault-id "$idsrc" "$file"
    echo "Decrypted $file IN PLACE. Edit it, then: scripts/vault.sh encrypt $scope"
    ;;
  encrypt)
    need_file
    ! is_encrypted "$file" || { echo "$file is already encrypted" >&2; exit 1; }
    ansible-vault encrypt --encrypt-vault-id "$scope" --vault-id "$idsrc" "$file"
    ;;
  *) echo "ERROR: unknown command $cmd" >&2; exit 2 ;;
esac
