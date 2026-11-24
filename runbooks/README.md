# Runbooks

Your site-specific operating procedures: how *you* add a node, rotate a
secret, recover a failed host, and so on. The framework's own docs cover how
Consigliere works; this directory is for how your fleet is run. Plain
markdown, one file per procedure. Start with `adding-a-node.md`.

These runbooks are generic. Names, domains and addresses in them are placeholders (`<host>`, `example.com`), so read them as patterns and write your own versions as you set things up.

- `adding-a-node.md`: bring a new host in
- `publish-a-service.md`: put a service on the internet behind Traefik
- `cmdr.md`: the fleet control page: hosts, live status and launch buttons in one place
- `run-reporting.md`: what you are told about reconcile runs, and how to set it up
- `exposure-watch.md`: scan the public addresses and alert on open ports that are not declared
- `what-consigliere-owns.md`: what each reconcile rewrites and what stays yours
- `variables.md`: how a variable in this repo becomes a setting inside an app
- `cli-reference.md`: every script in `scripts/`, its commands, flags and environment variables
- `admin-scripts.md`: what each helper script does, by task
