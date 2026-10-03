# Adding a node

1. Join it to Tailscale, then add it to `config/inventory/hosts.yml`: the key is
   its Tailscale hostname, `run:` lists the roles it should run.
2. If it runs an Arcane edge agent: generate the agent token in the Arcane
   manager, then put it in `config/vars/host/<hostname>.yml`.
3. Run the framework's `hosts/bootstrap/bootstrap.sh` on it (see the README).
4. `scripts/preflight.sh --strict` should pass before you push.
