# Tag manifests

What does a tag run? Each `util:` / `feat:` value in `inventory/hosts.yml` can have
a manifest here, one file per tag: `config/tags/<dimension>/<value>.yml`, for
example `config/tags/util/traefik.yml`. A manifest here overrides the
framework's manifest of the same name (`hosts/tags/` in the framework repo), and
adds tags the framework doesn't know.

```yaml
description: what this tag means          # optional, for people
order: 50                                 # lower runs earlier (default 50)
requires: [util/docker]                   # other tags this implies (optional)
conflicts: [prop/dns_other]               # tags that can't be combined with this one (optional)
roles: [my_rpc_proxy]                     # roles to run: framework roles or ./config/roles/<name>
vars: {timezone_name: UTC}                # variables handed to those roles/tasks (optional)
firewall: [{port: 8443, proto: tcp}]       # ports to open to the world on hosts with this tag (optional)
tasks: [files/extra.yml]                  # task files to run, relative to this manifest (optional)
```

- To change what a tag does, edit its manifest. To add a role, put it in
  `config/roles/<name>/` and name it in a manifest. `site.yml` is not touched.
- A tag with no manifest is just a class: it makes the group `util_<value>` to hang
  variables on (`vars/group/util_<value>.yml`) and nothing else runs.
- A typo such as `util: [traefk]` is a tag with no manifest, so nothing runs. Set
  `fleet_tags_strict: true` in `vars/group/all.yml` to make that an error (then
  give class-only tags an empty manifest: `roles: []`).
- Dimensions are `util`, `feat`, `cert` and `prop` by default; set `fleet_tag_dimensions`
  in `vars/group/all.yml` to change them (e.g. add `type`, then `config/tags/type/vps.yml`
  can run roles for every VPS).
- `cert: [<name>]` makes the host fetch that Cert Warden certificate (the framework's
  `cert/_default.yml` implies `feat/certwarden`). `<dimension>/_default.yml` is applied
  once whenever a host has any value in that dimension.
- `prop: [tz_est]` style tags are named bundles: the manifest picks a role and presets its
  variables with `vars:` (see `prop/tz_est.yml` and `prop/dns_quad9.yml`). `conflicts:` stops
  incompatible bundles being combined, with a clear error.
- Roles execute in `order`, then tag name. Roles are included once even when
  several tags name them.
