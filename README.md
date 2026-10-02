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
  vars/group/all/vault.yml secrets, ansible-vault ENCRYPTED. Start from vault.yml.example
  vars/host/<host>.yml     per-host values (e.g. an Arcane agent token)
  site.yml.example         optional: rename to site.yml to choose which roles run where
  roles/                   optional: your own roles/apps
runbooks/                  your own procedures
scripts/preflight.sh       checks for plaintext vaults and leftover placeholders
```

1. Decide your Tailscale tag names and map them in `config/inventory/groups.yml`
   (left side = the framework's group names; right side = your tags). Tag
   names are yours to choose, and they never appear in the public framework.
2. Replace every `CHANGEME` in `config/vars/` and create the vault:
   `cp config/vars/group/all/vault.yml.example config/vars/group/all/vault.yml`,
   fill it in, then `ansible-vault encrypt` it.
3. `scripts/preflight.sh --strict` should pass before you push.

## Deploy a host

On the host (Debian), with the framework's `hosts/bootstrap/bootstrap.sh`:

```bash
FRAMEWORK_REPO_URL=https://github.com/almadon/consigliere.git \
FLEET_CONFIG_REPO_URL=git@github.com:<you>/<fleet-name>.git \
FLEET_CONFIG_REGISTER_TOKEN=<token> \     # optional, see below
VAULT_PASSWORD_FILE=/path/to/vault-password \
./bootstrap.sh
```

The framework makes sure the host can read this repo: it generates a
read-only deploy key *on the host* (the private half never leaves it). With
`FLEET_CONFIG_REGISTER_TOKEN` (a GitHub token allowed to manage this repo's
deploy keys; used once, never stored) it registers the key for you. Without
it, the script prints the public key, and you add it under *Settings → Deploy
keys* (read-only); the script waits and continues once it works. The vault
password is the one thing that can't be generated, so supply it, then delete
your copy.

## Keeping up with the template

This is a starting point, not a live link: later changes to the template don't
flow into your repo. When the framework adds a role with new settings, its docs
say which variables to add here.
