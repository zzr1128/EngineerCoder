# -*- coding: utf-8 -*-
"""
Unified regression runner: discovers every ``sdk/*_check.py`` script and
executes each one in a subprocess with the repository root as working
directory (scripts resolve kit paths such as ``kits/cbased`` relative to
CWD). Prints a summary table and exits with the number of failed scripts,
so ``0`` means all green.

Probe scripts (``_probe_*.py``) are interactive investigations and are
intentionally excluded.
"""

import os
import subprocess
import sys
import time

if sys.stdout.encoding not in (None, 'utf-8', 'UTF-8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDK = os.path.join(_ROOT, 'sdk')
_PER_SCRIPT_TIMEOUT = 120  # seconds


def discover() -> list:
    names = []
    for name in sorted(os.listdir(_SDK)):
        if not name.endswith('_check.py'):
            continue
        if name.startswith('_probe_'):
            continue
        names.append(name)
    return names


def run_one(name: str) -> tuple:
    """Returns (status, elapsed_seconds, tail_of_output)."""
    path = os.path.join(_SDK, name)
    env = dict(os.environ)
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    env['PYTHONIOENCODING'] = 'utf-8'
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, path],
            cwd=_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=_PER_SCRIPT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        output = (exc.stdout or '') if isinstance(exc.stdout, str) else ''
        return 'TIMEOUT', elapsed, output[-800:]
    elapsed = time.perf_counter() - start
    if proc.returncode == 0:
        return 'PASS', elapsed, ''
    output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
    return 'FAIL', elapsed, output[-800:]


def main() -> int:
    names = discover()
    if not names:
        print('no check scripts discovered under sdk/')
        return 1

    print(f'running {len(names)} check scripts (cwd = repo root, timeout = '
          f'{_PER_SCRIPT_TIMEOUT}s each)\n')
    results = []
    for name in names:
        status, elapsed, tail = run_one(name)
        results.append((name, status, elapsed, tail))
        marker = 'PASS' if status == 'PASS' else status
        print(f'  [{marker:<7}] {name}  ({elapsed:.1f}s)')

    failed = [(name, status, tail) for name, status, _, tail in results
              if status != 'PASS']

    print('\n' + '=' * 64)
    print(f'{"script":<36} {"status":<9} {"time":>8}')
    print('-' * 64)
    for name, status, elapsed, _ in results:
        print(f'{name:<36} {status:<9} {elapsed:>7.1f}s')
    print('-' * 64)
    passed = len(results) - len(failed)
    print(f'total: {passed} passed, {len(failed)} failed')
    print('=' * 64)

    for name, status, tail in failed:
        print(f'\n--- failure detail: {name} ({status}) ---')
        print(tail if tail else '(no output captured)')

    return len(failed)


if __name__ == '__main__':
    sys.exit(main())
