#!/bin/bash
# run-arms.sh inside a bubblewrap sandbox in which /home is empty, so that a
# plugin's hooks cannot reach your files. Same arguments and environment as
# run-arms.sh; every plugin directory named in ARMS and OUTDIR must be
# outside /home (for example under /tmp).
#
#   ARMS="none:- skinflint:/tmp/x/skinflint ..." \
#     bash benchmarks/run-arms-sandboxed.sh OUTDIR [REPS] [MODEL]
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?usage: run-arms-sandboxed.sh OUTDIR [REPS] [MODEL]}
mkdir -p "$out"
out=$(cd "$out" && pwd)
claude=$(readlink -f "$(command -v claude)")
cfg=$(mktemp -d)
trap 'rm -rf "$cfg"' EXIT
cp "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" "$cfg/"
chmod 600 "$cfg/.credentials.json"

a=(--ro-bind / / --tmpfs /home --tmpfs /tmp --tmpfs /run --dev /dev --proc /proc
  --bind "$out" "$out" --bind "$cfg" "$cfg" --ro-bind "$claude" /tmp/bin/claude --ro-bind "$here" "$here"
  --chdir /tmp --die-with-parent)
[ -d /run/systemd/resolve ] && a+=(--ro-bind /run/systemd/resolve /run/systemd/resolve)
for arm in ${ARMS:?set ARMS}; do
  d=${arm#*:}
  [ "$d" != - ] && a+=(--ro-bind "$d" "$d")
done
for d in .ssh .aws .claude; do
  if bwrap "${a[@]}" test -e "$HOME/$d"; then echo "refusing to run: $HOME/$d is visible in the sandbox"; exit 2; fi
done
shift
bwrap "${a[@]}" env HOME=/tmp CLAUDE_CONFIG_DIR="$cfg" PATH="/tmp/bin:$PATH" bash "$here/run-arms.sh" "$out" "$@"
