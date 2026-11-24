#!/usr/bin/env bash
# Every Traefik route per proxy host and where it is defined. Usage: scripts/routes.sh [host]
# (the conflict check itself runs from scripts/preflight.sh; see scripts/routes_check.py)
here="$(dirname "$0")"
py="${ACCESS_PYTHON:-python3}"
if ! "$py" -c "import yaml" 2>/dev/null; then
  # The python that runs ansible: the first `ansible` on PATH that is a real Python script. A pyenv or Homebrew shim for it starts
  # with "#!/usr/bin/env bash" and is skipped, which is what `command -v ansible` alone would pick.
  for cand in $(type -ap ansible 2>/dev/null); do
    shebang="$(head -1 "$cand" 2>/dev/null | sed -n 's/^#! *//p')"
    case "$shebang" in */python*) if [ -x "${shebang%% *}" ]; then py="$shebang"; break; fi ;; esac
  done
fi
"$py" -c 'import yaml' 2>/dev/null || { echo "ERROR: no python with PyYAML found; set ACCESS_PYTHON to one (the interpreter that runs ansible, or a pyenv virtualenv's bin/python)" >&2; exit 1; }
exec "$py" "$here/routes_check.py" --show "$@"
