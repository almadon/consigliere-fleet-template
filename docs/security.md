# Security

## What protects the secrets

- Every secret is a file under `config/secrets/`, encrypted with sops to the age keys of the administrators and of only the hosts whose tags need it. `scripts/access.sh show` prints who can read what.
- Each host makes its own age key and its own read-only deploy key. Neither private half leaves the host.
- `scripts/preflight.sh`, also the pre-commit hook, refuses a secret that is not encrypted. It only protects a clone where `git config core.hooksPath .githooks` has been run.

## What to keep in mind

- Every host clones all of the ciphertext. The recipient lists decide what each can open.
- Removing a host stops future access only. It has already seen what it could read, so change those values and rotate the files.
- A push to the default branch is applied by the hosts on their next run. Anyone who can push here can change every host.

The framework's trust boundaries are in its [security document](https://github.com/almadon/Consigliere/blob/main/docs/security.md).
