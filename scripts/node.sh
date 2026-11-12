#!/usr/bin/env bash
# Add or change a node by answering questions: see scripts/node.py (or run with no arguments).
# Needs a python3 with PyYAML and Ansible's libraries: the one that runs ansible.
here="$(dirname "$0")"
py="${ACCESS_PYTHON:-python3}"
if ! "$py" -c 'import yaml, ansible' 2>/dev/null; then
  # The python that runs ansible: the first `ansible` on PATH that is a real Python script. A pyenv or Homebrew shim for it starts
  # with "#!/usr/bin/env bash" and is skipped, which is what `command -v ansible` alone would pick.
  for cand in $(type -ap ansible 2>/dev/null); do
    shebang="$(head -1 "$cand" 2>/dev/null | sed -n 's/^#! *//p')"
    case "$shebang" in */python*) if [ -x "${shebang%% *}" ]; then py="$shebang"; break; fi ;; esac
  done
fi
"$py" -c 'import yaml' 2>/dev/null || { echo "ERROR: no python with PyYAML found; set ACCESS_PYTHON to one (the interpreter that runs ansible, or a pyenv virtualenv's bin/python)" >&2; exit 1; }
exec "$py" "$here/node.py" "$@"
