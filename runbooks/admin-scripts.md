# Admin scripts

The full reference (every command, flag and environment variable) is in `cli-reference.md`; this page is the by-task overview.

Run from the root of this repo on your machine. Except `node.sh key` (which registers, commits and pushes), none of them commits or pushes; each shows what it changed, runs
`scripts/preflight.sh --strict`, and leaves the review to you. Every script has `--help`.

| Script | What it does |
|---|---|
| `scripts/fleet-run.sh HOSTS -- CMD` / `--status` / `--update` / `--reboot [--if-needed]` | Run a command, check status, apply package updates, or reboot hosts one at a time and wait for each to come back healthy, over SSH. `all` never includes Unraid. See `cli-reference.md`. |
| `scripts/reconcile-now.sh [hosts\|all] [--check] [--no-wait]` | Asks hosts to reconcile now instead of waiting for the 20-minute timer, waits, and prints each host's result, the fleet commit it ran and the changed tasks. `--check` runs the reconciler in check mode on the host (nothing changes) and lists what WOULD change. Needs SSH to the hosts: set `RECONCILE_SSH_OPTS` (falls back to `AUDIT_SSH_OPTS`). Unraid hosts run the reconciler container once. |
| `scripts/tag.sh add\|remove <dimension> <value> [--hosts all\|a,b] [--skip-types unraid]` | Adds or removes one tag value (for example `feat otel`) on hosts in the host table, syncs secret grants and runs the preflight. Does not commit. |
| `scripts/node.sh add <name>` | Interactive: asks what a new node is and runs, writes the host table (and its vars file), prints the steps to run on the node. |
| `scripts/node.sh key <name> <age-key>` | Finishes registration when the node prints its age key (grants its secrets). |
| `scripts/node.sh edit <name>` | Changes an existing node's tags or vars. |
| `scripts/audit.sh` | (Read-only: it never starts a reconcile; use `reconcile-now.sh` for that.) A matrix of what every node has and lacks against `config/standards.yml` (nodes in its `ignore:` list are skipped). Also: `missing <feature>`, `node <name>`, `live [--ssh]` (checks the real hosts), `onboard`. |
| `scripts/routes.sh [host]` | Lists every Traefik route per proxy host (names, backends, profiles) and the file each is defined in. The conflict check behind it also runs in `preflight.sh`. |
| `scripts/publish.sh` | Adds a Traefik route (and optionally a console tile). See `publish-a-service.md`. |
| `scripts/console.sh init` | Sets up the Muximux console. See `fleet-console.md`. |
| `scripts/notify.sh init [--hosts <host>\|all]` | Turns on run reporting through Pushover: asks for your user key and app token (hidden), tags hosts `feat: [apprise]`, stores the secret `apprise.notify`. See `run-reporting.md`. |
| `scripts/garage.sh init [--host <host>]` / `webui` | Sets up Garage (S3): tags the host `util: [garage]`, generates and encrypts the cluster secret, the admin API token and the web UI login. `webui` adds the last two to a secret made earlier. See `garage-s3.md`. |
| `scripts/observability.sh init [--host <host>]` | Sets up Loki and Grafana: asks for Grafana's Pocket ID client id and secret (hidden), generates an admin password, stores them as `grafana.server`, tags the host `util: [loki, grafana]`. See `observability.md`. |
| `scripts/beszel-add.sh --hosts <host>\|all\|a,b` | Rolls the Beszel agent out: tags hosts `prop: [beszel]` and stores the hub key and token (`secret beszel.agent`). Roll out in stages: one host first (it asks for the key and token), then `--hosts all`. `--replace` rotates the secret. |
| `scripts/cw-add.sh <certificate> [url]` | Tests a Cert Warden certificate's two API keys with a real download, then stores them as `cw.<name>`. The host must already carry `cert: [<name>]`. |
| `scripts/access.sh sync` / `add-host` / `remove-host` / `show` | Who can read which secret, derived from the host table. |
| `scripts/secrets.sh create\|edit\|view\|rotate <scope>` | Work with sops secrets. |
| `scripts/preflight.sh [--strict]` | Refuses plaintext secrets and placeholders; the commit hook. |

Hosts apply a push on their next reconcile (about 20 minutes), or immediately with `systemctl start fleet-reconcile`
on the host.
