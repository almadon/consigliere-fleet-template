# consigliere-fleet-template

A template for **your private fleet repo**, the other half of
[Consigliere](https://github.com/almadon/consigliere).

Consigliere (the framework) is public and generic: roles, a default
playbook, a console, bootstrap scripts. It contains nothing about *your*
fleet. This repo is where you say what you want from it and keep what must
stay private. It has two jobs:

1. **Customization**: your node taxonomy, which roles run where, your own
   apps/roles, and your runbooks.
2. **Secrets and variables**: per-group and per-host vars, plus the
   ansible-vault encrypted secrets.

Every host clones both repos on each reconcile, so this repo **must be
private** and each host needs read access to it. The framework arranges that
for you at bootstrap (see below).

## Create your private copy

A GitHub *fork* of a public repo can't be made private, so use the template
button instead. Either "Use this template" → Owner/Name → **Private**, or:

```bash
gh repo create <you>/<fleet-name> --private --template almadon/consigliere-fleet-template --clone
cd <fleet-name>
git config core.hooksPath .githooks        # refuses to commit a plaintext vault
```

(One-time, for whoever hosts the template: mark this repo as a *template
repository* in its GitHub settings.)

## Fill it in

```
config/
  inventory/groups.yml     YOUR tag names -> the framework's group names. Required.
  vars/group/*.yml         values per group (server address, ports, ...)
  vars/group/<scope>/vault.yml  one encrypted secrets file per scope (see Secrets)
  vars/host/<host>.yml     per-host values (e.g. an Arcane agent token)
  site.yml.example         optional: rename to site.yml to choose which roles run where
  roles/                   optional: your own roles/apps
runbooks/                  your own procedures
scripts/vault.sh           create/edit/view a scope's vault with the right id
scripts/preflight.sh       checks vaults are encrypted + correctly labelled, and for placeholders
```

1. Decide your Tailscale tag names and map them in `config/inventory/groups.yml`
   (left side = the framework's group names; right side = your tags). Tag
   names are yours to choose, and they never appear in the public framework.
2. Replace every `CHANGEME` in `config/vars/`, then create the vaults you need
   with `scripts/vault.sh create <scope>` (see Secrets below).
3. `scripts/preflight.sh --strict` should pass before you push.

## Deploy a host

On the host (Debian), with the framework's `hosts/bootstrap/bootstrap.sh`:

```bash
FRAMEWORK_REPO_URL=https://github.com/almadon/consigliere.git \
FLEET_CONFIG_REPO_URL=git@github.com:<you>/<fleet-name>.git \
FLEET_CONFIG_REGISTER_TOKEN=<token> \     # optional, see below
VAULT_PASSWORDS_DIR=/path/to/dir \          # one file per scope this host may read
./bootstrap.sh
```

The framework makes sure the host can read this repo: it generates a
read-only deploy key *on the host* (the private half never leaves it). With
`FLEET_CONFIG_REGISTER_TOKEN` (a GitHub token allowed to manage this repo's
deploy keys; used once, never stored) it registers the key for you. Without
it, the script prints the public key, and you add it under *Settings → Deploy
keys* (read-only); the script waits and continues once it works. Vault passwords can't be generated, so supply them (`VAULT_PASSWORDS_DIR`: one file
per scope, giving the host only the scopes it should read), then delete your copies.

## Secrets

Secrets are split into **scopes**, each its own encrypted file, so a host can
be given access to only what it needs and layers build on one another:

| Scope (vault id) | File | Who holds the password |
|---|---|---|
| `base` | `config/vars/group/all/vault.yml` | every host (keep it small) |
| `<group>` | `config/vars/group/<group>/vault.yml` | only hosts in that group |

The vault id is the group name (`base` for `all`), and it is also the name of
the password file a host is given. Ansible only loads a group's files for hosts
in that group, so a host never decrypts anything outside its scopes. A secret
shared by a set of hosts (e.g. Arkeep's server and agents) gets a group that is
exactly that set, plus a scope of the same name (see `arkeep` in `groups.yml`).

```bash
scripts/vault.sh create server_traefik   # encrypts vault.yml.example in place
scripts/vault.sh edit   server_traefik   # prompts, or reads ~/.config/consigliere/vault/<scope>
```

`scripts/preflight.sh` checks that every vault file is encrypted and that its
id matches its folder. Note that **every host clones the ciphertext**; the
passwords are what you control, so give each host only its scopes.

## Keeping up with the template

This is a starting point, not a live link: later changes to the template don't
flow into your repo. When the framework adds a role with new settings, its docs
say which variables to add here.
