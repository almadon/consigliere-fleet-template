# consigliere-fleet-template

A template for **your private fleet repo**, the other half of
[Consigliere](https://github.com/SerenIT-org/Consigliere).

Consigliere (the framework) is public and generic: roles, a default
playbook, a console, bootstrap scripts. It contains nothing about *your*
fleet. This repo is where you say what you want from it and keep what must
stay private. It has two jobs:

1. **Customization**: your node taxonomy, which roles run where, your own
   apps/roles, and your runbooks.
2. **Secrets and variables**: per-group and per-host vars, plus the
   sops-encrypted secrets.

Every host clones both repos on each reconcile, so this repo **must be
private** and each host needs read access to it. The framework arranges that
for you at bootstrap (see below).

## Create your private copy

A GitHub *fork* of a public repo can't be made private, so use the template
button instead. Either "Use this template" → Owner/Name → **Private**, or:

```bash
gh repo create <you>/<fleet-name> --private --template SerenIT-org/consigliere-fleet-template --clone
cd <fleet-name>
git config core.hooksPath .githooks        # refuses to commit a plaintext secret
```

(One-time, for whoever hosts the template: mark this repo as a *template
repository* in its GitHub settings.)

## Fill it in

```
config/
  inventory/hosts.yml      the host table: every host + type/site/util/feat. Required.
  inventory/groups.yml     turns the table's values into groups. Required.
  vars/group/*.yml         values per group (server address, ports, ...)
  secrets/<kind>/<name>.yml  sops-encrypted secrets (see Secrets)
  access.yml               admin and host age public keys (managed by scripts/access.sh)
  vars/host/<host>.yml     per-host values (e.g. an Arcane agent token)
  site.yml.example         optional: rename to site.yml to choose which roles run where
  roles/                   optional: your own roles/apps
runbooks/                  your own procedures
scripts/secrets.sh         create/edit/view/decrypt/encrypt/rotate a sops secret
scripts/access.sh          who may read which secret (add-host, sync, show)
scripts/preflight.sh       checks secrets are encrypted, .sops.yaml is current, and for placeholders
```

1. List your hosts in `config/inventory/hosts.yml` (key = the host's Tailscale
   hostname) with `type`, `site`, `util` (services it provides: `util: [traefik]` runs the
   Traefik role) and `feat` (agents it runs: `feat: [arkeep]` runs the Arkeep agent). `groups.yml` turns these
   into groups. Your names never appear in the public framework, and Tailscale
   tags are not used for grouping.
2. Replace every `CHANGEME` in `config/vars/`, then create the secrets you need
   with `scripts/secrets.sh create <scope>` (see Secrets below).
3. `scripts/preflight.sh --strict` should pass before you push.

## Deploy a host

On the host (Debian), with the framework's `hosts/bootstrap/bootstrap.sh`:

```bash
FRAMEWORK_REPO_URL=https://github.com/SerenIT-org/Consigliere.git \
FLEET_CONFIG_REPO_URL=git@github.com:<you>/<fleet-name>.git \
FLEET_CONFIG_REGISTER_TOKEN=<token> \     # optional, see below
./bootstrap.sh
```

The framework makes sure the host can read this repo: it generates a
read-only deploy key *on the host* (the private half never leaves it). With
`FLEET_CONFIG_REGISTER_TOKEN` (a GitHub token allowed to manage this repo's
deploy keys; used once, never stored) it registers the key for you. Without
it, the script prints the public key, and you add it under *Settings → Deploy
keys* (read-only); the script waits and continues once it works. It then prints the host's age public key for you to grant (see
Secrets). The first run is check-only; you approve the apply.

## Secrets

Secrets are **named files** encrypted with [sops](https://github.com/getsops/sops)
(age keys). A scope `<kind>.<name>` is the file `config/secrets/<kind>/<name>.yml`.
Each file is encrypted to the public keys of you (the admins) and of exactly the hosts
allowed to read it, so a host can decrypt only its own files, with a private key that
never leaves it. There are no shared passwords. Folders go big to small:

| Scope | File | Read by |
|---|---|---|
| `arkeep.agent` | `config/secrets/arkeep/agent.yml` | Arkeep server and agents (shared secret) |
| `arkeep.server` | `config/secrets/arkeep/server.yml` | the Arkeep server only |
| `arcane.server` | `config/secrets/arcane/server.yml` | the Arcane manager, if Ansible deploys it |
| `semaphore.server` | `config/secrets/semaphore/server.yml` | the Semaphore host |
| `cw.<name>` | `config/secrets/cw/<name>.yml` | hosts with `cert: [<name>]` |

**Who can read what is derived from the host table.** Each tag manifest in the
framework (`hosts/tags/`) lists the `secrets:` its roles need (`cert:` values become
`cw.<value>`). So adding `util: [arkeep]` to a host in `hosts.yml` and running
`scripts/access.sh sync` grants it the Arkeep secrets; removing the tag and syncing
revokes it. `scripts/access.sh show` prints the table. Secrets no tag implies go under
`extra_grants` in `config/access.yml`.

**Setting up (once, on your admin machine):** install `sops` and `age`, then
```bash
scripts/secrets.sh init-admin          # your age key (~/.config/sops/age/keys.txt) + registers you
```
(back that key up; with no admin key left, nothing can be re-encrypted). Set
`framework_dir` in `config/access.yml` (or `CONSIGLIERE_DIR`) to your checkout of the
framework, which `access.sh` reads for the manifests.

**Everyday:**
```bash
scripts/secrets.sh create arkeep.agent     # new file from its .example, encrypted
scripts/secrets.sh edit   arkeep.agent     # nano; re-encrypts on save
scripts/secrets.sh decrypt arkeep.agent    # decrypt IN PLACE to edit in an IDE ...
scripts/secrets.sh encrypt arkeep.agent    # ... then encrypt again (preflight refuses to commit plaintext)
```

**Adding a host:** `bootstrap.sh` generates the host's age key and prints its public half.
Then, here: `scripts/access.sh add-host <name> <key>`, `scripts/access.sh sync`, commit,
push. **Removing a host:** `scripts/access.sh remove-host <name>`, `sync`, push, and
`scripts/secrets.sh rotate <scope>` plus changing the actual secret values it could read
(it has seen them). `scripts/preflight.sh` (also the pre-commit hook) checks that every
secret is encrypted and that `.sops.yaml` is up to date. Note that every host clones all
the ciphertext; the recipient lists decide what each can open.

Tailscale auth keys are never stored: `bootstrap.sh` prompts for one.

## Keeping up with the template

This is a starting point, not a live link: later changes to the template don't
flow into your repo. When the framework adds a role with new settings, its docs
say which variables to add here.
