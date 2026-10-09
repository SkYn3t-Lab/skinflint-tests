#!/usr/bin/env python3
"""Rewrite the README's benchmark table rows from a results folder.

  python3 benchmarks/readme_tables.py README.md RESULTS_DIR TASKS.tsv

Each table is found by its header line and its rows are replaced; a header
that is not found exactly once aborts without writing.
"""
import glob, json, os, sys

readme, res = sys.argv[1], sys.argv[2]
A = json.load(open(res + '/questions/arms.json'))
G = json.load(open(res + '/agentic/agentic.json'))
ORDER = ['skinflint', 'chisle', 'ponytail', 'caveman']
LINK = {'chisle': '[chisle](https://github.com/JayPokale/Chisle)',
        'ponytail': '[ponytail](https://github.com/dietrichgebert/ponytail)',
        'caveman': '[caveman](https://github.com/JuliusBrussee/caveman)'}

cost = {}
for f in glob.glob(res + '/questions/runs/*__*__*.json'):
    arm = os.path.basename(f).split('__')[1]
    cost[arm] = cost.get(arm, 0) + json.load(open(f)).get('total_cost_usd', 0)
qcost = {a: round(100 * cost[a] / cost['none']) for a in cost}

def bold_low(vals, fmt='%d%%'):
    low = min(vals)
    return [('**' + fmt % v + '**') if v == low else fmt % v for v in vals]

ov, ag = A['overall'], G['groups']['agentic']
tables = {}

rows = []
for a in ORDER:
    o = ov[a]
    cells = ['%d%%' % o['total_pct'], '%d%%' % qcost[a], '%d%%' % o['avg_pct'],
             '%d%% (%s)' % (o['worst_pct'], o['worst_task']), str(o['backfires'])]
    if a == 'skinflint':
        cells = ['**%s**' % c for c in cells]
    rows.append('| %s | %s | %s |' % ('**skinflint**' if a == 'skinflint' else LINK[a], ' | '.join(cells), A['correct'][a]))
rows.append('| no plugin | 100%% | 100%% | 100%% | 100%% | 0 | %s |' % A['correct']['none'])
tables['| Plugin | Output tokens, all questions | Cost |'] = rows

rows = []
for label, k in (('Coding, short', 'coding/short'), ('Coding, long', 'coding/long'),
                 ('Explaining, short', 'explain/short'), ('Explaining, long', 'explain/long')):
    rows.append('| %s | %s |' % (label, ' | '.join(bold_low([A['by_size'][k][a]['total_pct'] for a in ORDER]))))
tables['| Kind of question | skinflint |'] = rows

kinds = {l.split('\t')[0]: l.split('\t')[1:3] for l in open(sys.argv[3]) if l.strip()}
rows, shortest = [], 0
for t, p in A['per_task'].items():
    vals = [p[a] for a in ORDER]
    shortest += vals[0] == min(vals)
    rows.append('| `%s` | %s, %s | %d | %s |' % (t, kinds[t][0], kinds[t][1], p['baseline_tokens'], ' | '.join(bold_low(vals, '%d'))))
tables['| Question | Kind | No plugin, tokens |'] = rows

rows = []
for a in ORDER:
    g = ag[a]
    cells = ['%d%%' % g[k] for k in ('cost_pct', 'out_pct', 'inp_pct', 'turns_pct', 'reply_pct')]
    if a == 'skinflint':
        cells = ['**%s**' % c for c in cells]
    rows.append('| %s | %s | %d/%d |' % ('**skinflint**' if a == 'skinflint' else LINK[a], ' | '.join(cells), g['passed'], g['graded']))
rows.append('| no plugin | 100%% | 100%% | 100%% | 100%% | 100%% | %d/%d |' % (ag['none']['passed'], ag['none']['graded']))
tables['| Plugin | Cost | Output tokens | Input tokens |'] = rows

text = open(readme).read()
lines = text.split('\n')

def replace_rows(header, rows, keep_first_cols=0):
    hits = [i for i, l in enumerate(lines) if l.startswith(header)]
    if len(hits) != 1:
        sys.exit('header not found exactly once: ' + header)
    i = hits[0] + 2
    j = i
    while j < len(lines) and lines[j].startswith('|'):
        j += 1
    if len(rows) != j - i:
        sys.exit('row count differs for: ' + header)
    lines[i:j] = rows

for h, r in tables.items():
    replace_rows(h, r)

# Per-task cost table: keep the task and prompt cells, replace the figures.
hits = [i for i, l in enumerate(lines) if l.startswith('| Task | What Claude was asked |')]
if len(hits) != 1:
    sys.exit('per-task cost header not found exactly once')
i, cheapest = hits[0] + 2, 0
while lines[i].startswith('|'):
    c = [x.strip() for x in lines[i].strip('|').split('|')]
    t = c[0].strip('`')
    p = G['per_task'][t]
    vals = [round(100 * p[a]['cost']['mean'] / p['none']['cost']['mean']) for a in ORDER]
    cheapest += vals[0] == min(vals)
    lines[i] = '| %s | %s | $%.2f | %s |' % (c[0], c[1], p['none']['cost']['mean'], ' | '.join(bold_low(vals, '%d')))
    i += 1

# "How it compares" rows.
def cmp_row(prefix, cells):
    hits = [k for k, l in enumerate(lines) if l.startswith(prefix)]
    if len(hits) != 1:
        sys.exit('compare row not found exactly once: ' + prefix)
    lines[hits[0]] = prefix + ' ' + ' | '.join(cells) + ' |'

cmp_row('| Questions: output tokens (% of no plugin) |', bold_low([ov[a]['total_pct'] for a in ORDER]))
cmp_row('| Questions: cost (% of no plugin) |', bold_low([qcost[a] for a in ORDER]))
cmp_row('| Questions: worst single one (% of no plugin) |', bold_low([ov[a]['worst_pct'] for a in ORDER]))
hits = [k for k, l in enumerate(lines) if l.startswith('| Questions: answers graded correct')]
if len(hits) != 1:
    sys.exit('graded row not found exactly once')
lines[hits[0]] = '| Questions: answers graded correct (no plugin %s) | %s |' % (A['correct']['none'], ' | '.join(A['correct'][a] for a in ORDER))
cmp_row('| Tool-using tasks: output tokens (% of no plugin) |', bold_low([ag[a]['out_pct'] for a in ORDER]))
cmp_row('| Tool-using tasks: cost (% of no plugin) |', bold_low([ag[a]['cost_pct'] for a in ORDER]))
cmp_row('| Tool-using tasks: checks passed |', ['%d/%d' % (ag[a]['passed'], ag[a]['graded']) for a in ORDER])

open(readme, 'w').write('\n'.join(lines))
print('questions: skinflint shortest on %d of %d; cost share %s' % (shortest, len(A['per_task']), qcost))
print('tool tasks: skinflint cheapest on %d of %d' % (cheapest, len(G['per_task']) - 3))
print('overall', {a: ov[a] for a in ORDER})
print('agentic', {a: {k: v for k, v in ag[a].items() if k.endswith('_pct')} for a in ORDER})
