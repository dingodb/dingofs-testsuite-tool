"""Summarize integration runs without inventing zero counts from unknown logs."""
import json
from pathlib import Path
import re
import sys


def event_counts(path):
    suites = {}
    with Path(path).open() as stream:
        for seq, line in enumerate(stream, 1):
            event = json.loads(line)
            if event.get('version') != 2 or event.get('seq') != seq:
                raise ValueError('invalid event sequence')
            if event.get('type') != 'suite_finished':
                continue
            data = event['data']
            keys = ('total', 'passed', 'failed', 'completed', 'skipped', 'known_bugs', 'suite_errors')
            if any(type(data.get(k)) is not int or data[k] < 0 for k in keys):
                raise ValueError('invalid suite counts')
            if data['passed'] + data['failed'] + data['skipped'] + data['known_bugs'] != data['completed'] or data['completed'] > data['total']:
                raise ValueError('inconsistent suite counts')
            suites[(event.get('child_id'), event.get('module'))] = data
    if not suites:
        raise ValueError('missing finished suite')
    total, passed, failed = (sum(d[k] for d in suites.values()) for k in ('total', 'passed', 'failed'))
    good = all(d['status'] == 'completed' and not d['suite_errors'] and d['completed'] == d['total'] for d in suites.values())
    return total, passed, failed, good


def text_counts(path):
    text = Path(path).read_text(errors='replace')
    if 'TEST SUITE SUMMARY' in text:
        blocks = text.split('TEST SUITE SUMMARY')[1:]
        total = passed = failed = errors = 0
        for block in blocks:
            def count(label, default=None):
                match = re.search(r'(?m)^.*?\b' + label + r':\s*(\d+)', block)
                if not match and default is None:
                    raise ValueError('missing text count')
                return int(match[1]) if match else default
            total += count('Total Cases')
            passed += count('Passed')
            failed += count('Failed')
            errors += count('Suite Errors', 0)
        if passed + failed > total:
            raise ValueError('inconsistent text counts')
        return total, passed, failed, not errors
    lines = re.findall(r'(?m)^\s+\S+:\s+\d+\s+passed.*$', text)
    if not lines:
        matches = re.findall(r'(?m)^=+.*\d+.*(?:passed|failed).*in [\d.]+.*$', text)
        lines = matches[-1:]
    if not lines:
        raise ValueError('unknown summary format')
    counts = {k: sum(int(n) for line in lines for n in re.findall(r'(\d+)\s+' + k, line))
              for k in ('passed', 'failed', 'skipped', 'error')}
    return sum(counts.values()), counts['passed'], counts['failed'], not counts['error']


def summarize(log, events, exit_code):
    try:
        total, passed, failed, good = event_counts(events) if events else text_counts(log)
        status = 'SUCCESS' if exit_code == 0 and total > 0 and failed == 0 and good else 'FAIL'
        return total, passed, failed, status
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 'unknown', 'unknown', 'unknown', 'FAIL' if exit_code else 'UNKNOWN'


if __name__ == '__main__':
    print(*summarize(sys.argv[1], sys.argv[2], int(sys.argv[3])))
