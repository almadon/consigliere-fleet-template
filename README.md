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
  inventory/hosts.yml      the host table: every host + type/site/util + run: [roles]. Required.
  inventory/groups.yml     turns the table's values into groups. Required.
  vars/group/*.yml         values per group (server address, ports, ...)
  secrets/<kind>/<name>.yml  encrypted secrets, vault id <kind>.<name> (see Secrets)
  vars/host/<host>.yml     per-host values (e.g. an Arcane agent token)
  site.yml.example         optional: rename to site.yml to choose which roles run where
  roles/                   optional: your own roles/apps
runbooks/                  your own procedures
scripts/vault.sh           create/edit/view/decrypt/encrypt a secret with the right id
scripts/preflight.sh       checks vaults are encrypted + correctly labelled, and for placeholders
```

1. List your hosts in `config/inventory/hosts.yml` (key = the host's Tailscale
   hostname) with `type`, `site`, `util` and a `run:` list naming the framework's
   groups (`arkeep_server`, ...) that host should run. `groups.yml` turns these
   into groups. Your names never appear in the public framework, and Tailscale
   tags are not used for grouping.
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

Secrets are **named files**, each with its own vault id, so a host can be given
access to only what it needs. A scope `<kind>.<name>` is the file
`config/secrets/<kind>/<name>.yml`, encrypted with vault id `<kind>.<name>`, and
that same name is the password file a host is given. Folders go big to small:

| Scope | File | Read by (needs the password) |
|---|---|---|
| `arkeep.agent` | `config/secrets/arkeep/agent.yml` | Arkeep server and agents (shared secret) |
| `arkeep.server` | `config/secrets/arkeep/server.yml` | the Arkeep server only |
| `arcane.server` | `config/secrets/arcane/server.yml` | the Arcane manager, if Ansible deploys it |
| `semaphore.server` | `config/secrets/semaphore/server.yml` | the Semaphore host |
| `cw.<name>` | `config/secrets/cw/<name>.yml` | hosts that list certificate `<name>` |

Roles load exactly the secrets they need. A host without a role's password
stops with a message saying which one, instead of running half-configured.
(Group-wide vault files, `config/vars/group/<group>/vault.yml`, still work for
secrets every member of a group should read, and `base` for every host; you
probably won't need them. Tailscale auth keys are never stored: `bootstrap.sh`
prompts for one.)

```bash
scripts/vault.sh create arkeep.agent    # encrypts the example in place
scripts/vault.sh edit   arkeep.agent    # nano; prompts, or reads ~/.config/consigliere/vault/<scope>
scripts/vault.sh decrypt arkeep.agent   # decrypt IN PLACE to edit in an IDE ...
scripts/vault.sh encrypt arkeep.agent   # ... and encrypt again afterwards
```

`scripts/preflight.sh` (also the pre-commit hook) checks that every secret is
encrypted and that its vault id matches its path. Note that **every host clones
the ciphertext**; the passwords are what you control, so give each host only its
scopes.

### Granting a certificate to specific hosts

`cw` stands for Cert Warden. Certificates are granted per host: a host reads
`cw.<name>` only if it lists `<name>` in `certwarden_agent_certs` (in
`vars/host/<host>.yml`), and only needs that password.

## Keeping up with the template

This is a starting point, not a live link: later changes to the template don't
flow into your repo. When the framework adds a role with new settings, its docs
say which variables to add here.
