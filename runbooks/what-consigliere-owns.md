# What Consigliere owns, and what is yours

Every host reconciles about every 20 minutes: it pulls the framework and this repo and makes the host match them. That only matters for the things the repo
declares. The rule of thumb:

- **A file that says "Managed by Ansible" is rewritten every run.** Edit it in this repo, never on the host.
- **Data an app keeps for itself is never touched**: its database, its uploads, the settings you click together in its UI. That is also why those settings
  are *not* in git: they are only as safe as your backups (Arkeep), so back those directories up.

cmdr's Launchpad shows the split with a badge on each tool:

| Badge | Meaning |
|---|---|
| **repo-managed** | the repo sets all of its settings; changes made in the app are put back at the next run |
| **shared** | the repo sets part of it (tiles, data sources, jobs); the rest is yours and is kept |
| **your settings** | only the deployment is managed; settings live inside the app |

(Names, meanings and colours: `cmdr_mgmt_kinds` in the framework role, overridable in `config/vars/group/util_cmdr.yml`; a tool gets its badge with `mgmt: repo | mixed | ui`.)

## Service by service

| Service | Repo owns | You own (kept across runs) |
|---|---|---|
| **CtrlZen** (Muximux) | the deployment, the sign-in settings and the listen address; the tiles in `util_muximux.yml` are only the starting set, written once on the first run (`muximux_repo_owns_tiles: false`) | everything else: tiles, groups, theme, navigation, health, users, set in its own UI. Set `muximux_repo_owns_tiles: true` to have the repo own the tiles it declares instead |
| **cmdr** | everything: the page, tools, commands, tag kinds, badges | nothing (read-only page) |
| **Traefik** (every proxy host) | all routes, middlewares, headers, certificates' wiring | nothing |
| **Grafana** | sign-in, the provisioned data sources (Loki, VictoriaMetrics), provisioned dashboards (read-only) | dashboards, folders, alert rules and users you create in the UI |
| **Apprise** | the container, its admin login, which names reach it | the channels, tags and keys you save in its admin panel (`/opt/apprise/config`) |
| **Loki, VictoriaMetrics** | the containers, retention, ports | the data |
| **Proxmox Backup Server** | the container, the admin password, and it creates the datastores, prune jobs, remotes and pull jobs listed in `util_pbs.yml` *if missing* | anything else you add; jobs that exist are not rewritten |
| **Arkeep, Beszel, Arcane, Pocket ID, Vaultwarden, Cert Warden, UniFi, Unraid, Proxmox VE** | the deployment (container, ports, agents, access) | all settings: policies, users, clients, vault items, certificates |
| **Hosts** (baseline) | users and SSH keys, firewall, automatic updates, the Tailscale join, the otel and other agents | files and services you add yourself that no role manages |

## If you changed something in an app and it vanished

It was a repo-managed or shared setting. Make the change in this repo (the file named in the table), commit and push; it applies at the next run
(`scripts/reconcile-now.sh <host>` to apply it now).

## If you want a setting to stop being managed

Remove it from the repo's variables. For CtrlZen tiles that also removes them from the console; for most other things the role simply stops writing it and
whatever is on the host stays as it is until you change it.

## Keeping the repo's copy of UI settings (two-way, by hand)

The repo should hold what the apps hold, without taking the UI away from you. `scripts/settings.sh` moves settings in either direction **only when you ask**, so an edit made in
the UI is never overwritten behind your back:

| Command | Direction | What it does |
|---|---|---|
| `scripts/settings.sh status` | none | says what differs between the live app and the repo's copy |
| `scripts/settings.sh pull` | UI → repo | saves the live settings to `config/state/<app>.yaml`; review with `git diff`, then commit |
| `scripts/settings.sh push --yes` | repo → UI | replaces the live settings with the repo's copy (a backup is kept next to the file) and restarts the app |

A rebuilt host starts from the repo's copy: the role seeds the app from it on its first run. Today this covers CtrlZen (`config/state/ctrlzen.yaml`); sign-in settings are never copied,
and a setting whose name looks like a secret stops the pull. Apprise (its channels hold tokens, so a copy would be encrypted) and Grafana dashboards are the next candidates.
