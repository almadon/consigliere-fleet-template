# Command-line reference (fleet repo)

Every script in `scripts/`, run from the root of this repo on your admin machine. `--help` on any of them prints its own summary.
Unless a row says so, **a script never commits or pushes**: it edits files, runs `scripts/preflight.sh --strict` and shows you the diff; you review, commit and push.
Host-side commands (`bootstrap.sh`, `reconcile.sh`, `fleet-notify`) are in the framework's `docs/cli-reference.md`.

Environment you may want in your shell profile:

| Variable | Used by | Meaning |
|---|---|---|
| `SOPS_AGE_KEY_FILE` | everything that touches secrets | Your admin age key (default `~/.config/sops/age/keys.txt`) |
| `RECONCILE_SSH_OPTS` | `reconcile-now.sh` | Replaces the default SSH options, for example `-o IdentitiesOnly=yes -i ~/.ssh/fleet_admin.pub` (falls back to `AUDIT_SSH_OPTS`). Unset = the scripts offer the fleet admin key themselves, see below |
| `AUDIT_SSH_OPTS` | `audit.sh live --ssh` | The same, for the audit |
| `ACCESS_PYTHON` | scripts that read YAML | A python3 with PyYAML (the scripts otherwise try the interpreter Ansible uses) |

### SSH from the scripts (and Bitwarden's agent)

`reconcile-now.sh` and `audit.sh live --ssh` connect as `root@<tailscale ip>`. Unless you set the variables above, they offer **the fleet's admin public key**
(the first `baseline_admin_ssh_keys` entry in `config/vars/group/all.yml`) with `IdentitiesOnly`, and your ssh agent supplies the matching private key, so they do not
depend on `~/.ssh/config`. Why: with `IdentitiesOnly yes` in your config, ssh offers only keys whose public file is listed as an `IdentityFile`; a key that lives only in
Bitwarden's agent has no such file, nothing is offered, and the server seems to "reject your key". The scripts also reuse one authenticated connection per host for five minutes (`ControlMaster`, private sockets in `~/.cache/fleet-ssh`), so an agent that approves every signature is asked once per host, not once per command. For your own `ssh` commands, either add a line naming the public key
(`IdentityFile ~/.ssh/fleet_admin.pub` with the public half saved from the agent: `ssh-add -L | grep '<your key comment>'`) to the `Host` block that covers the node (a block named
`myhost` does not match when you connect by IP address), or run `ssh -o IdentitiesOnly=yes -i ~/.ssh/fleet_admin.pub root@<name>`. Nodes accept that key for both `root` (Ansible's
`PermitRootLogin prohibit-password`) and, on Oracle's Ubuntu image, `ubuntu`.

## Nodes

### `scripts/node.sh`: add or change a node by answering questions
| Command | What it does |
|---|---|
| `node.sh add [name]` | Asks what the node is (type, site, what it runs), writes `hosts.yml` (and its vars file), checks it, prints the steps to run on the node. Can finish the registration when the node prints its age key |
| `node.sh edit <name>` | The same questions with the current answers, to change what an existing node runs |
| `node.sh key <name> [age-key]` | Finish registration: stores the node's age key, re-encrypts its secrets, **commits and pushes** (after asking) |

### `scripts/audit.sh`: what each node has and lacks (read-only)
| Command | What it does |
|---|---|
| `audit.sh` | Matrix of host x feature against `config/standards.yml`, plus the gaps |
| `audit.sh missing <feature>` | Hosts without a feature (`beszel`, `arcane`, `arkeep`, `traefik`, or any role name) and how to fix each |
| `audit.sh node <name>` | Everything declared about one host: tags, roles that run, secrets it reads, ports open to the internet, routes |
| `audit.sh live [--ssh]` | Tailnet versus `hosts.yml` (unmanaged nodes, vanished hosts); `--ssh` also checks declared containers run and the last reconcile result. Never starts a reconcile |
| `audit.sh onboard <name> [--type lxc\|vps\|vm\|metal\|unraid] [--docker] [--write]` | The exact entry and steps for a new node; `--write` adds it to `hosts.yml` |

### `scripts/tag.sh`: change a tag on many hosts
`tag.sh add|remove <dimension> <value> [--hosts all|a,b,c] [--skip-types unraid,macos] [--dry-run]`. Dimensions: `type org site util feat cert prop fw`.
Edits `hosts.yml`, runs `access.sh sync` and the preflight. Example: `tag.sh add feat otel --hosts all --skip-types unraid`. A tag whose role needs a secret that does not exist yet
makes those hosts fail their run; the feature scripts below create tag and secret together.

## Running things now

### `scripts/reconcile-now.sh`: reconcile hosts on demand
`reconcile-now.sh [hosts|all] [--check] [--no-wait] [--timeout SECONDS]`
- default: starts `fleet-reconcile` on each host (Unraid: runs the container once), waits, prints result, fleet commit and the changed tasks
- `--check`: runs the reconciler in check mode on the host and lists what **would** change; changes nothing
- `--no-wait`: start and return; `--timeout` (default 900 s) bounds the wait per host
- a host that is already reconciling is not started twice; offline hosts are reported. Needs SSH as root over the tailnet.

### `scripts/fleet-run.sh`: run things on hosts now
Nodes pull their own configuration, so nothing pushes commands to them; this does it over SSH (root, the fleet admin key), carefully.

| Command | What it does |
|---|---|
| `fleet-run.sh HOSTS -- COMMAND...` | Run a command on each host, in parallel (`--jobs N`, default 4; `--serial` for one at a time). Output is prefixed `[host]`; the summary shows each exit code and the tool exits non-zero if any failed |
| `fleet-run.sh HOSTS --status` | Uptime and load, reboot required, failed units, running containers, last reconcile result |
| `fleet-run.sh HOSTS --update` | `apt-get update` and `upgrade` (non-interactive, keeps existing config files), then reports whether a reboot is required |
| `fleet-run.sh HOSTS --reboot [--if-needed]` | Reboots **one host at a time**: waits until it is gone and back with a new boot id, then checks `systemctl is-system-running`, failed units and containers; stops at the first host that does not return (`--keep-going` to continue). `--if-needed` only reboots hosts that have `/var/run/reboot-required` |

`HOSTS` is a comma-separated list or `all`; **`all` never includes Unraid** (name it on purpose; `--update`/`--reboot` refuse it: reboot a NAS from its own UI). `all`, any reboot, and any run on more than one host
ask for confirmation unless you pass `--yes`. `--dry-run` prints the plan only. `--timeout S` (command/update default 1800, reboot default 600). `--address NAME=IP` overrides the tailnet lookup.
Examples: `fleet-run.sh all --status`; `fleet-run.sh all -- 'sshd -T | grep -E "^(passwordauthentication|permitrootlogin)"'`; `fleet-run.sh host1,host2 --update --yes`; `fleet-run.sh host1,host2 --reboot --if-needed`.
Tested against a throwaway Ubuntu machine: a failing command (exit 1), an update, a real reboot with the wait and health check, and the `--if-needed` skip.

### `scripts/routes.sh [host]`: every Traefik route
Prints, per proxy host, each route (host names, backend, security profile, name) and the file that defines it. The same code (`routes_check.py`) runs in the preflight and fails on a
repeated route name or two routes matching the same request.

### `scripts/publish.sh`: publish a service
`publish.sh [--host H] [--name N] [--domain D] [--backend URL] [--profile app|strict|relaxed|framed|none] [--tile "Group"]`: adds a route to `config/routes/<domain>.yml` (`via` the host)
and optionally a console tile. Anything not given is asked. Refuses a domain that is already routed. Prints the DNS and certificate reminders. See `publish-a-service.md`.

## Secrets and access

### `scripts/secrets.sh`
`secrets.sh init-admin [name]` (once: makes your admin age key) - `create|edit|view <scope>` - `decrypt <scope>` / `encrypt <scope>` (to work in an IDE; the preflight refuses to commit a decrypted file) - `rotate <scope>` (new data key; do after removing a reader) - `migrate <scope>` (old ansible-vault file to sops).
A scope is `<kind>.<name>` = `config/secrets/<kind>/<name>.yml`, for example `arkeep.agent`, `grafana.server`, `cw.example.com`. Read a value without showing the rest:
`sops --decrypt --extract '["garage_webui_password"]' config/secrets/garage/server.yml`.

### `scripts/access.sh`: who may read which secret
`access.sh show` - `add-admin <name> <age-public-key>` - `add-host <name> <age-public-key>` (the key `bootstrap.sh` printed) - `remove-host <name>` - `sync [--no-update] [--check]`.
Grants come from the tags in `hosts.yml` through the tag manifests; `sync` rewrites `.sops.yaml` and re-encrypts every secret to match. After `remove-host`, `rotate` what that host could read and change the values.

### `scripts/preflight.sh [--strict]`
Refuses plaintext or legacy secrets, a stale `.sops.yaml`, `CHANGEME` placeholders (fatal with `--strict`) and conflicting Traefik routes. The commit hook runs it (enable once per clone: `git config core.hooksPath .githooks`). Run `--strict` before you push.

### `scripts/cw-add.sh <certificate> [cert-warden-url]`
Stores a Cert Warden certificate's two API keys as the secret `cw.<name>` after testing them with a real download (HTTP 200). The certificate name must match Cert Warden exactly and at least one
host must already have `cert: [<name>]` in `hosts.yml`. Asks for both keys (hidden).

## Feature setup (tag + secret in one safe step)

| Script | Does |
|---|---|
| `console.sh init [--host <host>]` | Fleet console (Muximux): asks for the Pocket ID client id and secret, tags the host `util: [muximux]`, writes `muximux.server`. Env: `MUXIMUX_CLIENT_ID`, `MUXIMUX_CLIENT_SECRET` |
| `observability.sh init [--host <host>]` | Loki + Grafana: asks for Grafana's Pocket ID client, generates the admin password, tags `util: [loki, grafana]`, writes `grafana.server`. Env: `GRAFANA_CLIENT_ID`, `GRAFANA_CLIENT_SECRET` |
| `garage.sh init [--host <host>]` / `webui` | Garage (S3): tags `util: [garage]`, generates the cluster secret, admin token and web UI login in `garage.server`; `webui` adds the last two to a secret created earlier |
| `notify.sh init [--hosts <host>\|all\|a,b] [--dry-run] [--replace]` | Run reporting through Pushover: asks for the user key and app token, tags `feat: [apprise]` (skips Unraid and macOS), writes `apprise.notify`. Env: `PUSHOVER_USER`, `PUSHOVER_TOKEN` |
| `beszel-add.sh [--hosts all\|a,b] [--dry-run] [--replace]` | Beszel agents: asks for the hub key and token, tags `prop: [beszel]`, writes `beszel.agent`. Env: `BESZEL_KEY`, `BESZEL_TOKEN` |
| `exposure.sh init [--host <host>]` / `key` / `learn` / `check` / `run` | Exposure watch: `init` tags the scanner host `util: [exposure]` and stores your Shodan API key (asked, hidden; Enter = none, the free InternetDB is used) in `shodan.api`; `key` replaces it; `learn` scans now and prints what is open as YAML (nothing notified); `check` scans and prints findings against the declared ports; `run` runs the scheduled job now. See `exposure-watch.md` |
| `pbs.sh init [--host <host>]` | A second Proxmox Backup Server that pulls a primary: tags `util: [pbs]` and stores a generated admin password in `pbs.server`. Datastores, remote and pull job are fleet vars (`util_pbs.yml`). See `proxmox-backup.md` |
| `cmdr.sh init [--host <host>]` | The control page: asks for the Pocket ID client id and secret (hidden), generates a session secret, tags `util: [cmdr]`, writes `cmdr.server`. See `cmdr.md` |

All of them can be re-run safely; the ones that create a secret refuse to overwrite an existing one (use `--replace` where offered, or `secrets.sh edit`).

## SSH is key-only

`baseline_ssh_password_auth: false` in `config/vars/group/all.yml` makes the baseline role install the admin keys for root and write `/etc/ssh/sshd_config.d/10-consigliere.conf`
(`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`). It applies to every Debian and Ubuntu node; Unraid has its own sshd and is not covered.
Check what is really enforced: `scripts/fleet-run.sh all -- 'sshd -T | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin)"'`.
