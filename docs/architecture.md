# Architecture

![The framework repo and the private fleet repo are both pulled by every host](images/two-repos.svg)

Each host pulls two repos on a timer: the public framework, which holds the roles and tag manifests, and a private fleet repo with the host table, variables, routes and secrets. The reconciler merges them into one run directory, checks what would change, applies it, and skips the run when neither repo has changed. A host's tags in `config/inventory/hosts.yml` decide which roles it runs and which secrets it may read.

How the layers fit together is described in the framework's [architecture document](https://github.com/almadon/Consigliere/blob/main/docs/architecture.md).
