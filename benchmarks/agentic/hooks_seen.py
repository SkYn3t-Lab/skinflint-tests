#!/usr/bin/env python3
"""What the hooks did in one run, read from that run's own transcript.

  python3 benchmarks/agentic/hooks_seen.py CONFIG_DIR

Prints a JSON object with one entry per kind of hook record and event (for
example "hook_additional_context:UserPromptSubmit"): how many, how many
bytes of text they carried, and the first 60 bytes of the first one. A hook
that failed appears under its own kind with its error text. An arm whose
plugin never loaded is the no-plugin arm under another name, so the analyser
reports this for every run instead of trusting that --plugin-dir worked.
"""
import glob, json, os, sys

out = {}
for f in glob.glob(os.path.join(sys.argv[1], 'projects', '*', '*.jsonl')):
    for line in open(f, errors='replace'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get('attachment') or {}
        kind = str(a.get('type') or '')
        if d.get('type') != 'attachment' or not kind.startswith('hook'):
            continue
        c = a.get('content')
        if c is None:
            c = a.get('stdout') or a.get('stderr') or a.get('error') or ''
        text = '\n'.join(str(x) for x in c) if isinstance(c, list) else str(c)
        if kind != 'hook_additional_context' and a.get('stderr'):
            text += ' | stderr: ' + str(a.get('stderr'))
        e = out.setdefault(kind + ':' + str(a.get('hookEvent') or a.get('hookName') or '?'), {'count': 0, 'bytes': 0, 'first': ''})
        e['count'] += 1
        e['bytes'] += len(text.encode('utf-8'))
        if not e['first']:
            e['first'] = text[:60]
print(json.dumps(out))
