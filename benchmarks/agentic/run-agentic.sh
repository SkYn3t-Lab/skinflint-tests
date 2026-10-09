#!/bin/bash
# Agentic head-to-head: each task in tasks.tsv through `claude -p` with tools
# on, once per arm, REPS times. Every run gets a fresh copy of the generated
# project (make_fixture.py) and a throwaway config directory holding only
# your login, and happens inside a bubblewrap sandbox in which /home is
# empty, so neither Claude nor a plugin's hooks can reach your files. The
# arm is the only difference between two runs of a task.
#
#   ARMS="none:- skinflint:<dir> other:<dir> ..." \
#     bash benchmarks/agentic/run-agentic.sh OUTDIR [REPS] [MODEL]
#
# TASKS="id id ..." limits the run to those task ids.
#
# For each run it keeps OUTDIR/<task>__<arm>__<rep>.json, Claude Code's own
# result (tokens, cost, turns, final reply), and .check, the verdict of
# check.py on what the run left behind. Resumable: a run whose JSON exists
# is skipped. It stops by itself when the copied login has less than 25
# minutes left, so the copy never needs to refresh the token.
#
# Needs bubblewrap (bwrap), python3 with PyYAML, and whatever each plugin's
# hooks need (Node.js for some).
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?usage: run-agentic.sh OUTDIR [REPS] [MODEL]}
reps=${2:-2}
model=${3:-claude-sonnet-5-5}
arms=${ARMS:?set ARMS}
mkdir -p "$out"
out=$(cd "$out" && pwd)
claude=$(readlink -f "$(command -v claude)")
creds=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json
base=$(mktemp -d)
trap 'rm -rf "$base"' EXIT

minutes_left() {
  python3 -c "import json,time;print(int((json.load(open('$creds'))['claudeAiOauth']['expiresAt']/1000-time.time())/60))"
}

# The sandbox: the whole system read-only, /home, /tmp and /run empty, then
# only what a run needs put back. $1 is "net" or "nonet"; the rest is the
# command.
box() {
  local net=$1 work=$2 iso=$3
  shift 3
  local a=(--ro-bind / / --tmpfs /home --tmpfs /tmp --tmpfs /run --dev /dev --proc /proc
    --bind "$work" "$work" --bind "$iso" "$iso" --ro-bind "$claude" "$claude" --ro-bind "$here" "$here"
    --chdir "$work" --die-with-parent)
  [ -d /run/systemd/resolve ] && a+=(--ro-bind /run/systemd/resolve /run/systemd/resolve)
  [ "$net" = nonet ] && a+=(--unshare-net)
  [ -n "${PLUGIN_DIR:-}" ] && a+=(--ro-bind "$PLUGIN_DIR" "$PLUGIN_DIR")
  bwrap "${a[@]}" "$@"
}

cell() { # id prompt arm dir rep
  local f="$out/$1__$3__$5.json"
  [ -s "$f" ] && return
  local work iso
  work=$(mktemp -d "$base/work.XXXXXX")
  iso=$(mktemp -d "$base/iso.XXXXXX")
  python3 "$here/make_fixture.py" "$work"
  cp "$creds" "$iso/"
  chmod 600 "$iso/.credentials.json"
  local args=(-p "$2" --model "$model" --output-format json --max-turns 40
    --tools "Bash,Read,Grep,Glob,Edit,Write" --allowedTools "Bash,Read,Grep,Glob,Edit,Write")
  local PLUGIN_DIR=
  if [ "$4" != - ]; then
    PLUGIN_DIR=$4
    args+=(--plugin-dir "$4")
  fi
  PLUGIN_DIR=$PLUGIN_DIR box net "$work" "$iso" \
    timeout 900 env HOME="$iso" CLAUDE_CONFIG_DIR="$iso" "$claude" "${args[@]}" </dev/null > "$f.tmp" 2>/dev/null
  # A run that ended in an error (a usage limit, for one) is not a result.
  if [ -s "$f.tmp" ] && ! grep -q '"is_error":true' "$f.tmp"; then
    cp "$f.tmp" "$iso/result.json"
    PLUGIN_DIR= box nonet "$work" "$iso" python3 "$here/check.py" "$1" "$work" "$iso/result.json" > "$f.check" 2>/dev/null </dev/null
    [ -s "$f.check" ] || echo "FAIL check did not run" > "$f.check"
    python3 "$here/hooks_seen.py" "$iso" > "$f.hooks" 2>/dev/null
    mv "$f.tmp" "$f"
  else
    rm -f "$f.tmp"
    echo "  failed $1/$3/$5"
  fi
  rm -rf "$work" "$iso"
}

# Refuse to start unless the sandbox really hides the home directory.
probe=$(mktemp -d "$base/probe.XXXXXX")
seen=$(PLUGIN_DIR= box nonet "$probe" "$probe" sh -c 'ls -A /home/* 2>/dev/null | grep -v -e "^/home" -e "^$" | sort -u | tr "\n" " "')
case " $seen " in
  *" .ssh "*|*" .aws "*|*" .claude "*) echo "sandbox leak: /home shows: $seen" >&2; exit 2 ;;
esac
echo "sandbox ok; visible under /home: ${seen:-nothing}"
rmdir "$probe"

for rep in $(seq 1 "$reps"); do
  while IFS=$'\t' read -r id kind prompt; do
    [ -z "$id" ] && continue
    case " ${TASKS:-$id} " in *" $id "*) ;; *) continue ;; esac
    if [ "$(minutes_left)" -lt 25 ]; then echo "stopping: login expires soon; re-run later to resume"; exit 3; fi
    echo "$(date +%T) rep $rep $id"
    for a in $arms; do cell "$id" "$prompt" "${a%%:*}" "${a#*:}" "$rep" & done
    wait
  done < "$here/tasks.tsv"
done
echo done
