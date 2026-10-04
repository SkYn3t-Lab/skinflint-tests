#!/usr/bin/env python3
"""Analyse a run-agentic.sh output directory.

  python3 benchmarks/agentic/analyze-agentic.py RUNDIR [--json OUT.json]

Every figure is read from the result JSON Claude Code wrote for each run, or
from check.py's verdict on it. Per arm: how many runs passed their check,
and cost, output tokens, input tokens (fresh, cache writes and cache reads
together), turns and final-reply size, each as the sum over tasks of the
mean over repetitions, with the percentage of the no-plugin arm. A task
counts towards an arm's totals only when every arm has at least one run of
it, so the arms are compared on the same tasks. Then the same per task, with
the lowest and highest repetition, so the spread is visible.
"""
import glob, json, os, statistics as st, sys

rundir = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
kinds = {}
order = []
for line in open(os.path.join(here, 'tasks.tsv')):
    if line.strip():
        i, kind, _ = line.rstrip('\n').split('\t', 2)
        kinds[i] = kind
        order.append(i)

M = ('cost', 'out', 'inp', 'turns', 'reply')
cells = {}      # (task, arm) -> list of dicts
hook_log = {}   # arm -> list of (bytes of hook text, other hook record kinds)
errors = []
for f in sorted(glob.glob(os.path.join(rundir, '*__*__*.json'))):
    t, arm, rep = os.path.basename(f)[:-5].split('__')
    try:
        d = json.load(open(f))
    except Exception:
        errors.append((t, arm, rep, 'unreadable result'))
        continue
    if d.get('is_error'):
        errors.append((t, arm, rep, str(d.get('subtype') or d.get('result'))[:80]))
        continue
    u = d['usage']
    try:
        verdict = open(f + '.check').read().strip()
    except OSError:
        verdict = 'FAIL no check file'
    try:
        hooks = json.load(open(f + '.hooks'))
    except Exception:
        hooks = None
    injected = None if hooks is None else sum(v['bytes'] for k, v in hooks.items() if k.split(':')[0] in ('hook_success', 'hook_additional_context'))
    hook_log.setdefault(arm, []).append((injected, sorted(k for k in (hooks or {}) if not k.startswith(('hook_success', 'hook_additional_context')))))
    cells.setdefault((t, arm), []).append({
        'cost': d.get('total_cost_usd', 0.0), 'out': u.get('output_tokens', 0),
        'inp': u.get('input_tokens', 0) + u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0),
        'turns': d.get('num_turns', 0), 'reply': len((d.get('result') or '').encode('utf-8')), 'verdict': verdict, 'rep': rep})

arms = sorted({a for _, a in cells}, key=lambda a: (a != 'none', a != 'skinflint', a))
tasks = [t for t in order if all((t, a) in cells for a in arms)]
partial = [t for t in order if t not in tasks and any((t, a) in cells for a in arms)]


def mean(t, a, m):
    return st.mean(c[m] for c in cells[(t, a)])


def total(a, m, sel):
    return sum(mean(t, a, m) for t in sel)


res = {'arms': arms, 'tasks': tasks, 'left_out': partial, 'errors': errors, 'groups': {}, 'per_task': {}}
print('runs: %d   errors: %d   tasks compared: %d   left out (an arm has no run): %s' % (
    sum(len(v) for v in cells.values()), len(errors), len(tasks), ', '.join(partial) or 'none'))
for e in errors:
    print('  error  %s / %s / rep %s: %s' % e)

print('\nplugin loaded? text the hooks put into each run, from the run transcripts')
for a in arms:
    xs = hook_log.get(a, [])
    known = [b for b, _ in xs if b is not None]
    other = sorted({k for _, ks in xs for k in ks})
    print('%-10s runs %3d   with hook text %3d   bytes per run %s   other hook records: %s' % (
        a, len(xs), sum(b > 0 for b in known), ('%d-%d' % (min(known), max(known))) if known else 'not recorded', ', '.join(other) or 'none'))

for label, sel in (('all tasks', tasks), ('agentic', [t for t in tasks if kinds[t] == 'agentic']),
                   ('question', [t for t in tasks if kinds[t] == 'question'])):
    if not sel:
        continue
    print('\n%s (%d)' % (label, len(sel)))
    print('%-10s %9s  %16s  %18s  %20s  %12s  %16s' % ('arm', 'passed', 'cost $', 'output tokens', 'input tokens', 'turns', 'reply bytes'))
    g = {}
    for a in arms:
        graded = [c for t in sel for c in cells[(t, a)] if c['verdict'] != 'UNGRADED']
        npass = sum(c['verdict'] == 'PASS' for c in graded)
        row = {'passed': npass, 'graded': len(graded)}
        txt = '%-10s %4d/%-4d' % (a, npass, len(graded))
        for m, fmt, w in (('cost', '%.2f', 9), ('out', '%d', 11), ('inp', '%d', 13), ('turns', '%.1f', 6), ('reply', '%d', 9)):
            v = total(a, m, sel); b = total('none', m, sel) if 'none' in arms else 0
            row[m] = v; row[m + '_pct'] = round(100 * v / b) if b else None
            txt += '  %*s %4s' % (w, fmt % v, ('%d%%' % row[m + '_pct']) if b else '')
        g[a] = row
        print(txt)
    res['groups'][label] = g

print('\nper task: mean over repetitions (lowest-highest), then each arm as %% of none')
for m, name in (('cost', 'cost $'), ('out', 'output tokens'), ('reply', 'reply bytes')):
    print('\n' + name)
    print('%-9s' % 'task' + ''.join('%26s' % a for a in arms))
    for t in tasks:
        txt = '%-9s' % t
        for a in arms:
            xs = [c[m] for c in cells[(t, a)]]
            v = st.mean(xs); b = mean(t, 'none', m) if 'none' in arms else 0
            f = '%.2f' if m == 'cost' else '%d'
            txt += '%26s' % ((f + ' (' + f + '-' + f + ') %3d%%') % (v, min(xs), max(xs), round(100 * v / b) if b else 0))
            res['per_task'].setdefault(t, {}).setdefault(a, {})[m] = {'mean': v, 'min': min(xs), 'max': max(xs)}
        print(txt)

print('\nfailed checks')
none = True
for t in order:
    for a in arms:
        for c in cells.get((t, a), []):
            if c['verdict'].startswith('FAIL'):
                none = False
                print('  %s / %s / rep %s: %s' % (t, a, c['rep'], c['verdict'][5:]))
if none:
    print('  none')
if '--json' in sys.argv:
    json.dump(res, open(sys.argv[sys.argv.index('--json') + 1], 'w'), indent=1)
