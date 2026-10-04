#!/usr/bin/env python3
"""Build the throwaway project the agentic benchmark works on.

  python3 benchmarks/agentic/make_fixture.py DIR

Everything is generated, the same bytes every time, so that every run of
every arm starts from an identical project. Each agentic task in tasks.tsv
has one planted problem here, and check.py knows what a correct result is.
"""
import os, sys

root = sys.argv[1]


def put(rel, text, mode=0o644):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as fh:
        fh.write(text)
    os.chmod(p, mode)


put('CLAUDE.md', '''# stockroom

A small inventory service: a Python package (`app/`), its tests (`tests/`),
operations scripts (`scripts/`), a compose file and sample logs (`logs/`).

Conventions:
- Run the tests with `python3 -m unittest discover -s tests -q`.
- Every compose service sets `mem_limit` and pins its image to a version tag,
  never `latest`.
- Scripts that send mail call `send(subject, body)` from `scripts/notify.py`,
  never `smtplib` directly.
- The version is written in `VERSION`, `app/__init__.py`, `README.md` and the
  top entry of `CHANGELOG.md`; they change together.
''')

put('VERSION', '1.3.2\n')
put('app/__init__.py', '__version__ = "1.3.2"\n')
put('README.md', '''# stockroom 1.3.2

Inventory service.

## Backup

    scripts/backup.sh SOURCE DEST

Copies SOURCE into a dated folder under DEST. Options: none.
''')
put('CHANGELOG.md', '''# Changelog

## 1.3.2
- Fix rounding in stock valuation.

## 1.3.1
- Add low-stock report.
''')

# bugfix and review: merge() overwrites instead of summing; low_stock() leaves
# out a quantity equal to the threshold.
put('app/inventory.py', '''"""Stock arithmetic."""


def merge(items):
    """Combine (sku, qty) pairs, summing the quantities of repeated SKUs,
    keeping first-seen order."""
    order = []
    total = {}
    for sku, qty in items:
        if sku not in total:
            order.append(sku)
            total[sku] = 0
        total[sku] = qty
    return [(sku, total[sku]) for sku in order]


def low_stock(stock, threshold):
    """SKUs whose quantity is at or below the threshold, sorted."""
    return sorted(sku for sku, qty in stock.items() if qty < threshold)


def value(stock, prices):
    """Total value of the stock, rounded to cents."""
    return round(sum(qty * prices[sku] for sku, qty in stock.items()), 2)
''')
put('tests/__init__.py', '')
put('tests/test_inventory.py', '''import unittest

from app.inventory import low_stock, merge, value


class TestInventory(unittest.TestCase):
    def test_merge_sums_repeats(self):
        self.assertEqual(merge([("a", 1), ("b", 2), ("a", 3)]), [("a", 4), ("b", 2)])

    def test_merge_keeps_order(self):
        self.assertEqual(merge([("z", 1), ("a", 1)]), [("z", 1), ("a", 1)])

    def test_low_stock_includes_threshold(self):
        self.assertEqual(low_stock({"a": 5, "b": 6, "c": 0}, 5), ["a", "c"])

    def test_value(self):
        self.assertEqual(value({"a": 3, "b": 1}, {"a": 0.1, "b": 2.5}), 2.8)


if __name__ == "__main__":
    unittest.main()
''')

# dryrun: backup.sh has no --dry-run option, and the README says so.
put('scripts/backup.sh', '''#!/bin/sh
# backup.sh SOURCE DEST: copy SOURCE into DEST/<date>/
set -eu
src=${1:?usage: backup.sh SOURCE DEST}
dest=${2:?usage: backup.sh SOURCE DEST}
target=$dest/$(date +%F)
mkdir -p "$target"
cp -R "$src/." "$target/"
echo "backed up $src to $target"
''', 0o755)

# mail: two of the five senders bypass notify.py.
put('scripts/notify.py', '''"""The one place mail is sent from."""
import smtplib
from email.message import EmailMessage


def send(subject, body, to="ops@example.com"):
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subject, "stockroom@example.com", to
    m.set_content(body)
    with smtplib.SMTP("localhost", 25) as s:
        s.send_message(m)
''')
for name, direct in (('report_low_stock', False), ('nightly_summary', True), ('disk_alert', False),
                     ('order_reminder', True), ('audit_export', False)):
    if direct:
        body = '''import smtplib
from email.message import EmailMessage


def main():
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = "%s", "stockroom@example.com", "ops@example.com"
    m.set_content("see attached")
    with smtplib.SMTP("localhost", 25) as s:
        s.send_message(m)
''' % name
    else:
        body = '''from notify import send


def main():
    send("%s", "see attached")
''' % name
    put('scripts/%s.py' % name, '"""%s job."""\n%s\n\nif __name__ == "__main__":\n    main()\n' % (name, body))
put('scripts/rotate_logs.py', '"""Rotates logs; sends nothing."""\nimport os\n\n\ndef main():\n    for f in os.listdir("logs"):\n        print(f)\n\n\nif __name__ == "__main__":\n    main()\n')

# compose: cache and worker have no mem_limit; worker and proxy use latest.
svc = [('web', 'stockroom/web:1.3.2', '512m'), ('api', 'stockroom/api:1.3.2', '768m'), ('db', 'postgres:16.4', '1g'),
       ('cache', 'valkey/valkey:8.0', None), ('worker', 'stockroom/worker:latest', None), ('proxy', 'nginx:latest', '128m')]
out = ['services:']
for name, image, mem in svc:
    out += ['  %s:' % name, '    image: %s' % image, '    restart: unless-stopped']
    if mem:
        out.append('    mem_limit: %s' % mem)
    out.append('    networks: [stock]')
out += ['networks:', '  stock: {}', '']
put('docker-compose.yml', '\n'.join(out))

# logs: the api exits because the report-export job filled the disk.
lines = []
for i in range(4200):
    sec = i * 3
    ts = '2026-03-09T%02d:%02d:%02d' % (2 + sec // 3600, (sec // 60) % 60, sec % 60)
    if 1300 <= i < 1460 and i % 4 == 0:
        lines.append('%s INFO  job=report-export wrote /var/lib/stockroom/exports/part-%05d.csv (512 MB)' % (ts, i))
    elif i == 1381:
        lines.append('%s WARN  disk /var/lib/stockroom at 91%%' % ts)
    elif i == 1470:
        lines.append('%s WARN  disk /var/lib/stockroom at 99%%' % ts)
    elif i == 1480:
        lines.append('%s ERROR db: could not extend file "base/16384/2619": No space left on device' % ts)
    elif i == 1481:
        lines.append('%s ERROR api: transaction aborted, shutting down worker pool' % ts)
    elif i == 1482:
        lines.append('%s FATAL api: exiting (status 1)' % ts)
    elif i > 1482 and i % 40 == 0:
        lines.append('%s ERROR proxy: upstream api refused connection' % ts)
    elif i % 97 == 0:
        lines.append('%s WARN  cache: slow command (%d ms)' % (ts, 100 + i % 50))
    else:
        who = ('web', 'api', 'proxy')[i % 3] if i < 1482 else ('web', 'proxy')[i % 2]   # the api serves nothing once it has exited
        lines.append('%s INFO  %s request id=%06d status=200 ms=%d' % (ts, who, i, 5 + i % 40))
put('logs/service.log', '\n'.join(lines) + '\n')

# disk: data/exports holds nearly all of the space.
for d, n, size in (('data/thumbnails', 40, 2000), ('data/exports', 6, 400000), ('data/cache', 25, 3000), ('data/uploads', 12, 9000)):
    for k in range(n):
        put('%s/f%03d.bin' % (d, k), 'x' * size)
