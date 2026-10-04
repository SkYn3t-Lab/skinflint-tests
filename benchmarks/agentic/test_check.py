#!/usr/bin/env python3
"""Prove check.py can fail and can pass.

  python3 benchmarks/agentic/test_check.py

Builds the fixture and checks every agentic task against it untouched, with
an empty reply: all eight must FAIL. Then applies a correct solution to each
task, with a reply stating the planted fact, and all eight must PASS. A
checker that passed the untouched project, or failed a correct one, would
make every figure built on it meaningless.
"""
import json, os, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
TASKS = ('bugfix', 'logs', 'dryrun', 'compose', 'mail', 'bump', 'disk', 'review')


def verdicts(work, reply):
    r = os.path.join(work, '.result.json')
    json.dump({'result': reply}, open(r, 'w'))
    out = {t: subprocess.run([sys.executable, os.path.join(here, 'check.py'), t, work, r],
                             capture_output=True, text=True).stdout.strip() for t in TASKS}
    os.remove(r)
    return out


def sub(work, rel, old, new):
    p = os.path.join(work, rel)
    s = open(p).read()
    assert old in s, (rel, old)
    open(p, 'w').write(s.replace(old, new))


bad = 0
with tempfile.TemporaryDirectory() as work:
    subprocess.run([sys.executable, os.path.join(here, 'make_fixture.py'), work], check=True)
    for t, v in verdicts(work, '').items():
        ok = v.startswith('FAIL')
        bad += not ok
        print('%-8s untouched -> %-60s %s' % (t, v[:60], 'ok' if ok else 'WRONG: must fail'))

    sub(work, 'app/inventory.py', 'total[sku] = qty', 'total[sku] += qty')
    sub(work, 'app/inventory.py', 'qty < threshold', 'qty <= threshold')
    open(os.path.join(work, 'scripts/backup.sh'), 'w').write('''#!/bin/sh
set -eu
dry=0
if [ "${1:-}" = --dry-run ]; then dry=1; shift; fi
src=${1:?usage: backup.sh [--dry-run] SOURCE DEST}
dest=${2:?usage: backup.sh [--dry-run] SOURCE DEST}
target=$dest/$(date +%F)
if [ $dry = 1 ]; then find "$src" -type f | sed "s|^|would copy |"; exit 0; fi
mkdir -p "$target"
cp -R "$src/." "$target/"
echo "backed up $src to $target"
''')
    sub(work, 'README.md', 'Options: none.', 'Options: `--dry-run` lists what would be copied.')
    sub(work, 'docker-compose.yml', 'image: valkey/valkey:8.0\n', 'image: valkey/valkey:8.0\n    mem_limit: 256m\n')
    sub(work, 'docker-compose.yml', 'image: stockroom/worker:latest\n', 'image: stockroom/worker:1.3.2\n    mem_limit: 512m\n')
    sub(work, 'docker-compose.yml', 'nginx:latest', 'nginx:1.27')
    for s in ('nightly_summary', 'order_reminder'):
        open(os.path.join(work, 'scripts/%s.py' % s), 'w').write(
            'from notify import send\n\n\ndef main():\n    send("%s", "see attached")\n\n\nif __name__ == "__main__":\n    main()\n' % s)
    sub(work, 'VERSION', '1.3.2', '1.4.0')
    sub(work, 'app/__init__.py', '1.3.2', '1.4.0')
    sub(work, 'README.md', 'stockroom 1.3.2', 'stockroom 1.4.0')
    sub(work, 'CHANGELOG.md', '## 1.3.2', '## 1.4.0\n- Add a --json flag to the low-stock report.\n\n## 1.3.2')
    reply = ('The report-export job filled the disk, so the database could not write and the api exited. '
             'data/exports holds nearly all of the space. merge() overwrites the quantity and low_stock() '
             'leaves out a quantity equal to the threshold.')
    fixed = verdicts(work, reply)
    # review must see the file unchanged, so it is checked on a fresh copy.
    with tempfile.TemporaryDirectory() as clean:
        subprocess.run([sys.executable, os.path.join(here, 'make_fixture.py'), clean], check=True)
        fixed['review'] = verdicts(clean, reply)['review']
    for t, v in fixed.items():
        ok = v == 'PASS'
        bad += not ok
        print('%-8s solved    -> %-60s %s' % (t, v[:60], 'ok' if ok else 'WRONG: must pass'))
print('%d wrong' % bad)
sys.exit(1 if bad else 0)
