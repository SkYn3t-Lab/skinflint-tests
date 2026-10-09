#!/usr/bin/env python3
"""Report a run-multiturn.sh output directory.

  python3 benchmarks/multiturn/analyze-multiturn.py RUNDIR [OUT.json]

For each arm: output tokens and reply bytes by position in the session
(quarters of the prompt list), each as a share of the first arm named
"none". Both orders are in every quarter, so each quarter holds every
prompt the same number of times in every arm. Also what the hooks added
per session, so an arm whose plugin never loaded is visible.
"""
import collections, glob, json, os, sys

run = sys.argv[1]
ids = {o: open(os.path.join(run, o + '.ids')).read().split() for o in ('fwd', 'rev')}
turns = collections.defaultdict(list)   # arm -> [(position, task, out_tokens, reply_bytes)]
cost = collections.defaultdict(float)
hooks = collections.defaultdict(lambda: collections.defaultdict(list))
sessions = collections.Counter()
for f in sorted(glob.glob(os.path.join(run, '*__*__*.jsonl'))):
    order, arm, rep = os.path.basename(f)[:-6].split('__')
    res = [d for d in map(json.loads, open(f)) if d.get('type') == 'result']
    sessions[arm] += 1
    cost[arm] += res[-1].get('total_cost_usd') or 0
    for i, d in enumerate(res):
        turns[arm].append((i, ids[order][i], d['usage']['output_tokens'], len((d.get('result') or '').encode())))
    try:
        for k, v in json.load(open(f + '.hooks')).items():
            if k.startswith('hook_additional_context'):
                hooks[arm][k.split(':')[1]].append(v['bytes'])
    except Exception:
        pass

n = len(ids['fwd'])
q = lambda i: min(3, i * 4 // n)
arms = sorted(turns, key=lambda a: (a != 'none', a))
out = {'sessions': dict(sessions), 'arms': {}}
print('sessions per arm: %s; %d prompts per session' % (dict(sessions), n))
for label, col in (('output tokens', 2), ('reply bytes', 3)):
    print('\n%s, share of none, by position in the session' % label)
    print('%-10s %14s %14s %14s %14s %14s' % ('arm', 'prompts 1-%d' % (n // 4), '%d-%d' % (n // 4 + 1, n // 2),
                                           '%d-%d' % (n // 2 + 1, 3 * n // 4), '%d-%d' % (3 * n // 4 + 1, n), 'all'))
    base = None
    for a in arms:
        s = [sum(t[col] for t in turns[a] if q(t[0]) == k) / sessions[a] for k in range(4)]
        s.append(sum(s))
        if a == 'none':
            base = s
        cells = ['%7d %4d%%' % (v, round(100 * v / b)) if b else '%7d' % v for v, b in zip(s, base or [0] * 5)]
        print('%-10s %14s %14s %14s %14s %14s' % (a, *cells))
        out['arms'].setdefault(a, {})[label] = {'per_session': s, 'share': [round(100 * v / b) for v, b in zip(s, base)] if base else None}
print('\ncost per session $: ' + ', '.join('%s %.2f' % (a, cost[a] / sessions[a]) for a in arms))
for a in arms:
    out['arms'][a]['cost_per_session'] = cost[a] / sessions[a]
    out['arms'][a]['hook_bytes_per_session'] = {k: sum(v) / len(v) for k, v in hooks[a].items()}
    print('hooks added, bytes per session, %-10s %s' % (a, out['arms'][a]['hook_bytes_per_session'] or 'nothing'))
if len(sys.argv) > 2:
    json.dump(out, open(sys.argv[2], 'w'), indent=1)
