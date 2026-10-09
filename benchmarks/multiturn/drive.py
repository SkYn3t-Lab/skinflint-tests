#!/usr/bin/env python3
"""Feed a `claude -p --input-format stream-json` process one prompt at a time.

  python3 drive.py PROMPTS.jsonl COMMAND [ARG...]

Writes one line of PROMPTS.jsonl to the command, copies what the command
prints to stdout until its result for that prompt arrives, then writes the
next. Sending every prompt at once would let the command answer several of
them in one turn.
"""
import subprocess, sys

p = subprocess.Popen(sys.argv[2:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
for prompt in open(sys.argv[1]):
    p.stdin.write(prompt)
    p.stdin.flush()
    for line in p.stdout:
        sys.stdout.write(line)
        if '"type":"result"' in line:
            break
    else:
        break
    sys.stdout.flush()
p.stdin.close()
sys.stdout.write(p.stdout.read())
sys.exit(p.wait())
