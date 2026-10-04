#!/usr/bin/env python3
"""Decide whether one run did its task, by inspecting what it left behind.

  python3 benchmarks/agentic/check.py TASK WORKDIR RESULT.json

Prints one line: PASS, FAIL <reason>, or UNGRADED. No model takes part: an
agentic task is checked by running or reading the files in WORKDIR, and the
three tasks that only ask for an explanation are checked for the one fact
planted in the fixture. A question task has no planted fact and is UNGRADED.
"""
import json, os, re, subprocess, sys, tempfile

task, work, result = sys.argv[1:4]
try:
    reply = (json.load(open(result)).get('result') or '')
except Exception:
    reply = ''
low = reply.lower()


def read(rel):
    try:
        return open(os.path.join(work, rel)).read()
    except OSError:
        return ''


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=60, **kw)


def original(rel):
    """The file as the fixture generator writes it."""
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, os.path.join(here, 'make_fixture.py'), d], check=True, capture_output=True)
        return open(os.path.join(d, rel)).read()


def bugfix():
    if read('tests/test_inventory.py') != original('tests/test_inventory.py'):
        return 'the tests were edited'
    r = run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
    return None if r.returncode == 0 else 'tests still fail'


def logs():
    if 'report-export' not in low and 'report export' not in low:
        return 'does not name the report-export job'
    if not re.search(r'disk|space', low):
        return 'does not mention the full disk'


def dryrun():
    if '--dry-run' not in read('README.md'):
        return 'README does not mention --dry-run'
    ok = False
    for args in (['--dry-run', 'src', 'dst'], ['src', 'dst', '--dry-run'], ['src', '--dry-run', 'dst']):
        with tempfile.TemporaryDirectory(dir=work) as t:
            os.makedirs(os.path.join(t, 'src')); os.makedirs(os.path.join(t, 'dst'))
            open(os.path.join(t, 'src', 'a.txt'), 'w').write('a')
            r = subprocess.run(['sh', os.path.join(work, 'scripts/backup.sh')] + args, cwd=t, capture_output=True, text=True, timeout=60)
            copied = any(fs for _, _, fs in os.walk(os.path.join(t, 'dst')))
            if r.returncode == 0 and not copied and 'a.txt' in r.stdout + r.stderr:
                ok = True
    if not ok:
        return '--dry-run copies, fails, or does not list the file'
    with tempfile.TemporaryDirectory(dir=work) as t:
        os.makedirs(os.path.join(t, 'src')); os.makedirs(os.path.join(t, 'dst'))
        open(os.path.join(t, 'src', 'a.txt'), 'w').write('a')
        r = subprocess.run(['sh', os.path.join(work, 'scripts/backup.sh'), 'src', 'dst'], cwd=t, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not any('a.txt' in fs for _, _, fs in os.walk(os.path.join(t, 'dst'))):
            return 'a normal backup no longer copies'


def compose():
    import yaml
    try:
        svc = yaml.safe_load(read('docker-compose.yml'))['services']
    except Exception:
        return 'docker-compose.yml no longer parses'
    if sorted(svc) != ['api', 'cache', 'db', 'proxy', 'web', 'worker']:
        return 'services changed: ' + ','.join(sorted(svc))
    for name, s in svc.items():
        if not s.get('mem_limit'):
            return name + ' has no mem_limit'
        image = str(s.get('image') or '')
        tag = image.rsplit(':', 1)[1] if ':' in image else ''
        if not tag or tag == 'latest':
            return name + ' image is not pinned'


def mail():
    for s in ('nightly_summary', 'order_reminder'):
        t = read('scripts/%s.py' % s)
        if 'smtplib' in t:
            return s + ' still uses smtplib'
        if not re.search(r'\bsend\(', t):
            return s + ' does not call send()'
    if 'smtplib' not in read('scripts/notify.py'):
        return 'notify.py was broken'
    for s in ('nightly_summary', 'order_reminder', 'report_low_stock', 'disk_alert', 'audit_export', 'notify'):
        if run([sys.executable, '-m', 'py_compile', 'scripts/%s.py' % s]).returncode != 0:
            return s + ' does not compile'


def bump():
    if read('VERSION').strip() != '1.4.0':
        return 'VERSION is not 1.4.0'
    if '1.4.0' not in read('app/__init__.py') or '1.3.2' in read('app/__init__.py'):
        return 'app/__init__.py not bumped'
    if '1.4.0' not in read('README.md'):
        return 'README not bumped'
    c = read('CHANGELOG.md')
    a, b = c.find('## 1.4.0'), c.find('## 1.3.2')
    if a < 0 or b < 0 or a > b:
        return 'CHANGELOG has no 1.4.0 entry above 1.3.2'
    if 'json' not in c[a:b].lower():
        return 'CHANGELOG entry does not mention the --json flag'


def disk():
    if 'exports' not in low:
        return 'does not name data/exports'


def review():
    if read('app/inventory.py') != original('app/inventory.py'):
        return 'the file was changed'
    if 'merge' not in low:
        return 'does not mention merge()'
    if 'low_stock' not in low:
        return 'does not mention low_stock()'


checks = {f.__name__: f for f in (bugfix, logs, dryrun, compose, mail, bump, disk, review)}
if task not in checks:
    print('UNGRADED')
else:
    try:
        why = checks[task]()
    except Exception as e:
        why = 'check crashed: %r' % (e,)
    print('PASS' if not why else 'FAIL ' + why)
