# From a variable in this repo to a setting inside an app

A value you write in this repo reaches an app in three hops. Nothing is magic: each hop is a file you can open.

```
 fleet repo (yours)                   framework role (shared)                         the app
 config/vars/group/util_muximux.yml → hosts/roles/muximux/defaults/main.yml  ──►  templates/docker-compose.yml.j2  ──►  MUXIMUX_OIDC_ADMIN_GROUPS=admins.frontend
   muximux_oidc_admin_groups:           muximux_oidc_admin_groups: [Muximux-Admins]     MUXIMUX_OIDC_ADMIN_GROUPS: {{ ... | join(',') }}
   [admins.frontend]                    (the default; yours wins)
```

1. **Your value** lives in `config/vars/group/<tag>.yml` (everything tagged `util: [muximux]`) or `config/vars/host/<host>.yml` (one host). Host beats group beats the role's default.
2. **The role's `defaults/main.yml`** is the catalogue: every setting the role understands, with its default and a comment saying what it does and which app setting it becomes. Variables are named `<role>_<thing>`; a name starting with `_` is the role's own working value, not a setting.
3. **The role's template** (`templates/docker-compose.yml.j2` or `config.yaml.j2`) is where the variable is turned into the app's own name: an environment variable, a line in the app's config file. Open it and search for the variable to see exactly what the app receives.
4. **The app's own documentation** says what that setting means. A setting an app does not have has no variable (Muximux has no profile-picture setting, so the role has none).

## Worked example: CtrlZen (Muximux) sign-in

| You set (fleet repo) | Role variable | Muximux sees | What it does |
|---|---|---|---|
| `muximux_oidc_admin_groups: [admins.frontend]` | same | `MUXIMUX_OIDC_ADMIN_GROUPS=admins.frontend` | members of that group become admins |
| `muximux_oidc_groups_claim: groups` | same | `MUXIMUX_OIDC_GROUPS_CLAIM=groups` | which claim in the token carries the groups |
| `muximux_oidc_scopes_extra: []` | same | `MUXIMUX_OIDC_SCOPES=openid,profile,email,groups` | scopes: the four standard ones are **always** sent, `groups` included; this list only adds |
| `muximux_oidc_username_claim` / `_email_claim` / `_display_name_claim` | same | `MUXIMUX_OIDC_*_CLAIM` | left empty, Muximux uses its own defaults |

The same rule holds for Grafana (`grafana_server_oidc_scopes`) and cmdr: **the groups scope is always requested**, because the groups claim is how admin and editor roles are decided.
Environment settings win over what is in an app's own config file, and a setting that comes from the environment shows as locked in the app's UI.

## Finding out what a host really gets

- The rendered result is on the host: `scripts/fleet-run.sh <host> --yes -- 'cat /opt/<service>/docker-compose.yml'` (it holds secrets for some services: look, do not paste).
- The repo's view of every route, tile and variable file: `scripts/routes.sh <host>`; the page `cmdr` lists what each host is tagged with and what that tag brings.
- When a setting seems ignored: it is set in a host file that overrides the group file, or the app is user-editable and its own UI value won (`runbooks/what-consigliere-owns.md`).
