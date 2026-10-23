import json
from pathlib import Path
import re
import sys


def verify_run(data, expected_sha, platform):
    if data.get('head_sha') != expected_sha:
        raise ValueError('Compiler source SHA does not match the requested revision')
    if data.get('status') != 'completed' or data.get('conclusion') != 'success':
        raise ValueError('Compiler run is not a completed success')
    if data.get('event') not in ('push', 'workflow_dispatch'):
        raise ValueError('Compiler artifacts must come from a push or dispatch, not a PR merge build')
    matches = [job for job in data.get('jobs', []) if job.get('name') == platform]
    if len(matches) != 1 or matches[0].get('conclusion') != 'success':
        raise ValueError(f'Native compiler job {platform} did not pass exactly once')


def main():
    if len(sys.argv) != 4 or not re.fullmatch(r'[0-9a-f]{40}', sys.argv[2]):
        raise SystemExit('usage: compiler_provenance.py RUN_JSON FULL_SHA PLATFORM')
    try:
        verify_run(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')), sys.argv[2], sys.argv[3])
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
    print('Verified native compiler run, source SHA, event and platform job')


if __name__ == '__main__':
    main()
