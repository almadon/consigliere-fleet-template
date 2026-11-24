# Publish a service

Put a service on the internet behind one of the fleet's Traefik proxies:

    scripts/publish.sh

It asks (or take `--host --domain --backend --profile --name --tile`):

1. **Proxy host**: any host with `util: [traefik]` (your edge hosts).
2. **Domain**: refused if it is already routed anywhere in `config/vars/`.
3. **Backend**: `http://container:port` for a container on the proxy host's Docker networks
   (`traefik_server_networks`), or `http://100.x.y.z:port` for a service on another tailnet node.
4. **Security profile**: `app` (default: headers, HSTS, tight CSP), `relaxed` (no CSP), `strict`, `framed`
   (may be put in a frame), `none`.
5. **Console tile** (optional): a group name from `muximux_groups` in `config/vars/group/util_muximux.yml`.

It appends one line to the domain's file, `config/routes/<domain>.yml` (named after the certificate that covers the name; created if needed; with `via: <host>` when the host is not
that file's default), then runs the preflight and shows
the diff. Then you do the two things it cannot:

- **DNS**: `*.example.com` points at your main proxy host. For another proxy host (for example `ark.example.com`) add an A record
  to that host's public address. Other zones need their own record.
- **Certificate**: the proxy host must fetch a certificate covering the domain (`cert: [...]` in the host table).

Commit and push; the host serves the route after its next reconcile. If a page misbehaves, check the browser console
for "Content Security Policy" and set that route to `profile: relaxed`.

Routes with options the wizard does not ask (redirects, static sites, extra middlewares, path rules) are edited by hand
in the same file; see the traefik_server role README in the framework.

## Safety nets against conflicting routes

1. `publish.sh` refuses a domain that is already routed anywhere in `config/vars/`.
2. `scripts/preflight.sh` (the commit hook, and `--strict` before deploying) runs `scripts/routes_check.py`: per proxy host
   it resolves every `traefik_server_routes*` variable that host would see and fails on a repeated route name or two
   routes matching the same request (same host or same rule). A domain routed on two different hosts is only a warning
   (normal while a service moves).
3. On the host, the `traefik_server` role asserts the same thing before it writes anything, and the reconciler's
   check pass runs before the apply: a conflict stops that host's run with a message naming the duplicate, and the
   running Traefik keeps its last good configuration.
