#!/bin/bash
# Long-session benchmark: all the prompts of tasks.tsv as ONE conversation,
# one prompt after another in a single `claude -p` process (drive.py sends
# each prompt only when the answer to the one before has arrived), once per arm,
# REPS times, in two orders (file order, and reversed) so that every prompt
# is asked both early and late. It answers what the single-prompt benchmark
# cannot: whether a plugin still holds late in a session.
#
#   ARMS="none:- skinflint:<dir> other:<dir> ..." \
#     bash benchmarks/multiturn/run-multiturn.sh OUTDIR [REPS] [MODEL]
#
# Tools are off, so nothing is read or written by the model. Every session
# runs in a throwaway config directory holding only your login. For each
# session it keeps OUTDIR/<order>__<arm>__<rep>.jsonl, Claude Code's own
# event stream (one result per prompt), and .hooks, what the hooks put in.
# Resumable: a session whose file exists is skipped. The arms of one session
# run concurrently.
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?usage: run-multiturn.sh OUTDIR [REPS] [MODEL]}
reps=${2:-2}
model=${3:-claude-sonnet-5-5}
arms=${ARMS:?set ARMS}
tasks=${TASKS_FILE:-$here/../tasks.tsv}
mkdir -p "$out"
out=$(cd "$out" && pwd)
creds=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json
base=$(mktemp -d)
trap 'rm -rf "$base"' EXIT

minutes_left() {
  python3 -c "import json,time;print(int((json.load(open('$creds'))['claudeAiOauth']['expiresAt']/1000-time.time())/60))"
}

python3 - "$tasks" "$base" <<'EOF'
import json, sys
rows = [l.rstrip('\n').split('\t') for l in open(sys.argv[1]) if l.strip()]
for name, order in (('fwd', rows), ('rev', rows[::-1])):
    with open('%s/%s.in' % (sys.argv[2], name), 'w') as f:
        for r in order:
            f.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': r[3]}}) + '\n')
    open('%s/%s.ids' % (sys.argv[2], name), 'w').write(' '.join(r[0] for r in order) + '\n')
EOF
cp "$base"/*.ids "$out/"

session() { # order arm dir rep
  local f="$out/$1__$2__$4.jsonl"
  [ -s "$f" ] && return
  local iso
  iso=$(mktemp -d "$base/iso.XXXXXX")
  cp "$creds" "$iso/"
  chmod 600 "$iso/.credentials.json"
  local args=(-p --input-format stream-json --output-format stream-json --verbose --model "$model" --tools "")
  [ "$3" != - ] && args+=(--plugin-dir "$3")
  ( cd "$iso" && timeout 5400 env HOME="$iso" CLAUDE_CONFIG_DIR="$iso" python3 "$here/drive.py" "$base/$1.in" claude "${args[@]}" ) > "$f.tmp" 2>/dev/null
  if [ "$(grep -c '"type":"result"' "$f.tmp")" = "$(wc -l < "$base/$1.in")" ] && ! grep -q '"is_error":true' "$f.tmp"; then
    python3 "$here/../agentic/hooks_seen.py" "$iso" > "$f.hooks" 2>/dev/null
    mv "$f.tmp" "$f"
  else
    mv "$f.tmp" "$f.partial"
    echo "  incomplete $1/$2/$4"
  fi
  rm -rf "$iso"
}

for rep in $(seq 1 "$reps"); do
  for order in fwd rev; do
    if [ "$(minutes_left)" -lt 30 ]; then echo "stopping: login expires soon; re-run later to resume"; exit 3; fi
    echo "$(date +%T) rep $rep $order"
    for a in $arms; do session "$order" "${a%%:*}" "${a#*:}" "$rep" & done
    wait
  done
done
echo done
