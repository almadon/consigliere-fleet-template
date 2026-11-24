# cmdr: the fleet's control page

`https://cmdr.ctrl.example.com`, served by the host tagged `util: [cmdr]`. One page that shows every host (from this repo: what it is, what it provides and runs, its routes),
its live status (from Loki: is it sending logs, did its last reconcile succeed, the exposure scan) and a launch button for every admin tool,
including the names that only open on the LAN or tailnet (for example an internal-only domain). Read-only: it shows and links. The Muximux console (`cz.ctrl.example.com`)
can embed it. Pocket ID cannot be shown in a frame, so the first load of a session inside Muximux shows a small "Sign in" panel that opens the sign-in in a tab and reloads itself when done; after that the frame works until the session expires (8 hours).

## First setup

1. **Pocket ID:** create a confidential OIDC client. Callback URL `https://cmdr.ctrl.example.com/auth/callback`; scopes `openid profile email groups`;
   allow the group `admins.sysops` (`cmdr_admin_groups`; add a `users.sysops` group to `cmdr_viewer_groups` for read-only access).
2. `scripts/cmdr.sh init` (pass `--host <host>`). It asks for the client id and secret (hidden), generates a session secret, tags the host
   `util: [cmdr]`, stores the secret `cmdr.server` and runs the preflight. Review, commit, push, then `scripts/reconcile-now.sh <host>`.
3. Open the page. DNS and the certificate are the `*.ctrl.example.com` ones already in place.

## Day to day

- **Add or change a button:** `cmdr_tools` (fleet-wide) and `cmdr_host_links` (per host; `{host}` and `{host_q}`) in `config/vars/group/util_cmdr.yml`.
- **New hosts and routes appear by themselves** at the next reconcile of the cmdr host (the page reads this repo's host table and route files).
- **Rotate the client secret:** `scripts/secrets.sh edit cmdr.server`.
- **Status says "incomplete":** Loki is unreachable (it runs on its own host). The inventory and links still show; the status chips fill in when Loki answers.

## What the status means

| Chip | Meaning |
|---|---|
| green dot | the host sent logs to Loki in the last 10 minutes |
| red dot | it should (it has `feat: [otel]`) and sent none for 10 minutes: down, or its agent stopped |
| grey dot | not expected to report (no `otel` feature, for example a host without the tag) or status unavailable |
| reconcile: in sync / changed N | the last `fleet-reconcile` recap in the last 24 h: nothing changed / N tasks changed things |
| reconcile: failed | the recap had failed or unreachable tasks: open the host's logs |
| exposure | the last scan of each public address: open ports that are not declared in `config/vars/group/util_exposure.yml` are red |

## Not yet

Actions (reconcile now, a drift check) are deliberately left out of this first version: a page that can run commands on every host is root on the fleet.
When they come they will be few, named, signed-in and logged, and run through Semaphore or short-lived SSH certificates, never a root key held by the page.
