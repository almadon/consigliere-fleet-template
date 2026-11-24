# Run reporting (Pushover)

Every host reconciles itself about every 20 minutes. With the Apprise feature, a host tells you what happened:

| Event | Pushover | Message |
|---|---|---|
| A run fails (check or apply) | priority **high** (tag `alert`) | The failing task and its error. The same failure is repeated at most every 6 hours. |
| The first good run after a failure | low (tag `info`) | "reconcile recovered" |
| An applied run that changed something | low (tag `info`) | The names of the changed tasks (up to 8) |

Every run's full output is also kept on the host in `/opt/fleet-reconcile/last-run.log`, and in the journal
(`journalctl -u fleet-reconcile`). Hosts without Apprise (Unraid, macOS) stay silent but still log.

## Set up

1. In Pushover, create an Application (any name) and note its **application token**; your **user key** is on the dashboard.
2. `scripts/notify.sh init --hosts <host>`. It asks for both (hidden), tags that host `feat: [apprise]`, stores them encrypted as
   `apprise.notify` and runs the preflight. Review, commit, push.
3. After that host reconciles, on it: `fleet-notify "test" "hello"` should reach your phone.
4. `scripts/notify.sh init --hosts all` tags the other Debian hosts (it keeps the secret and re-encrypts it for them). Review, commit, push.

## Tuning

- Quieter: set `RECONCILE_NOTIFY_CHANGES=0` in `/etc/fleet-reconcile.env` on a host to drop the "applied N change(s)" notes.
- Rotate the Pushover keys: `scripts/notify.sh init --replace`.
- Later, Grafana can take over alerting. These messages are a floor that does not depend on Grafana or Loki being up.
