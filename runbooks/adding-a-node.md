# Adding a node

> **Quickest way:** `scripts/node.sh add <name>` asks what the node is and what it should run, writes the host table
> (and its vars file) for you, checks it, prints the exact steps to run on the node, and `scripts/node.sh key <name>`
> finishes the registration when the node prints its age key. `scripts/node.sh edit <name>` changes an existing
> node. `scripts/audit.sh` shows what every node has and lacks. The manual steps below are what the wizard does.

1. Join it to Tailscale, then add it to `config/inventory/hosts.yml`: key = its
   Tailscale hostname, with `type`, `site`, `util` (services it provides) and `feat` (agents it runs).
2. Arcane edge agent: in the Arcane manager (`arc.a64.one`) run the edge-agent
   wizard, then put the token in `config/vars/host/<hostname>.yml` as
   `arcane_agent_token` (start from `empros.yml`).
3. On the host, run the framework's `hosts/bootstrap/bootstrap.sh`:

       FRAMEWORK_REPO_URL=https://github.com/almadon/Consigliere.git \
       FLEET_CONFIG_REPO_URL=git@github.com:tmeuze/fleet64.git \
       FLEET_CONFIG_REGISTER_TOKEN=<optional: lets it register its own deploy key> \
       ./bootstrap.sh

   Without the token it prints the host's deploy key and waits; add it as a
   **read-only** deploy key on `tmeuze/fleet64`. It then prints the host's age public
   key: run `scripts/access.sh add-host <name> <key>` and `scripts/access.sh sync`,
   commit and push, then press Enter. The first run is check-only; approve the apply.
4. `scripts/preflight.sh --strict` should pass before you push config changes.
