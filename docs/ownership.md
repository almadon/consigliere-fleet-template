# Ownership

What this repo manages and who controls each thing. What the framework manages on a host is in its [ownership document](https://github.com/almadon/Consigliere/blob/main/docs/ownership.md).

| Thing | Owner | Mechanism | Why | Where to change it | Backup |
|---|---|---|---|---|---|
| Host table, variables, tags | This repo | Read and applied every run | One reviewed place for what each host is | `config/inventory/`, `config/vars/`, `config/tags/` | git history |
| Traefik routes | This repo | Rewritten on the proxy hosts every run | A hand edit would be lost, and could clash | `config/routes/` | git history |
| Secret files | This repo, encrypted | Decrypted on the host during a run | Reviewable without being readable | `scripts/secrets.sh` | git history; the admin age key needs its own safe backup |
| `.sops.yaml` | Generated | Rewritten by `scripts/access.sh sync` | Recipients follow from tags | The host table, `config/access.yml` | Regenerated |
| Data inside services | The service and you | Not touched | Consigliere runs services, it does not own their data | The app | Your backups. This repo is not one |
