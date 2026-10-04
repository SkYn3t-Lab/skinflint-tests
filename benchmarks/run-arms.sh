#!/bin/bash
# Head-to-head benchmark: the same 20 prompts through `claude -p`, once per
# arm, REPS times. Arms: none (no plugin), and each plugin loaded as a real
# plugin with --plugin-dir. Every call runs in a throwaway config directory
# holding only your login, so no personal instructions, settings or other
# plugins take part: the arm is the only difference.
#
#   ARMS="none:- skinflint:<dir> other:<dir> ..." \
#     bash benchmarks/run-arms.sh OUTDIR [REPS] [MODEL]
#
# TASKS="id id ..." limits the run to those task ids, for example to give
# close results more repetitions.
#
# To test on your own prompts and under your own instructions:
#   TASKS_FILE=<file>  a task file of your own (id, kind, size, prompt,
#                      separated by tabs) in place of tasks.tsv
#   PERSONAL=<dir>     a directory copied into the throwaway config before
#                      each run, for example holding your CLAUDE.md, so that
#                      every arm runs under your instructions
#   NO_TOOLS=1         run with every tool disabled, so that a prompt taken
#                      from a real session cannot act on anything
#
# Resumable: a cell whose JSON exists is skipped. The arms of one prompt run
# concurrently, like the original design this follows. It stops by itself
# when the copied login has less than 25 minutes left, so the copy never
# needs to refresh the token.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?usage: run-arms.sh OUTDIR [REPS] [MODEL]}
reps=${2:-2}
model=${3:-claude-sonnet-5-5}
arms=${ARMS:?set ARMS}
mkdir -p "$out"

iso=$(mktemp -d)
trap 'rm -rf "$iso"' EXIT
cp "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json" "$iso/"
chmod 600 "$iso/.credentials.json"
[ -n "${PERSONAL:-}" ] && cp -R "$PERSONAL/." "$iso/"

minutes_left() {
  python3 -c "import json,time;print(int((json.load(open('$iso/.credentials.json'))['claudeAiOauth']['expiresAt']/1000-time.time())/60))"
}

cell() { # id prompt arm dir rep
  local f="$out/$1__$3__$5.json"
  [ -s "$f" ] && return
  local args=(-p "$2" --model "$model" --output-format json)
  [ "$4" != - ] && args+=(--plugin-dir "$4")
  [ "${NO_TOOLS:-}" = 1 ] && args+=(--tools "")
  ( cd "$iso" && timeout 300 env HOME="$iso" CLAUDE_CONFIG_DIR="$iso" claude "${args[@]}" </dev/null ) > "$f.tmp" 2>/dev/null
  if [ -s "$f.tmp" ]; then mv "$f.tmp" "$f"; else rm -f "$f.tmp"; echo "  failed $1/$3/$5"; fi
}

for rep in $(seq 1 "$reps"); do
  while IFS=$'\t' read -r id kind size prompt; do
    [ -z "$id" ] && continue
    case " ${TASKS:-$id} " in *" $id "*) ;; *) continue ;; esac
    if [ "$(minutes_left)" -lt 25 ]; then echo "stopping: login expires soon; re-run later to resume"; exit 3; fi
    echo "$(date +%T) rep $rep $id"
    for a in $arms; do cell "$id" "$prompt" "${a%%:*}" "${a#*:}" "$rep" & done
    wait
  done < "${TASKS_FILE:-$here/tasks.tsv}"
done
echo done
