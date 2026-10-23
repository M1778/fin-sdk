import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('compiler_provenance', Path(__file__).with_name('compiler_provenance.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SHA = 'a' * 40


class ProvenanceTests(unittest.TestCase):
    def valid(self):
        return {'head_sha': SHA, 'status': 'completed', 'conclusion': 'success', 'event': 'workflow_dispatch',
                'jobs': [{'name': 'linux-x86_64', 'conclusion': 'success'}]}

    def test_valid_dispatch_and_push(self):
        for event in ('workflow_dispatch', 'push'):
            run = self.valid()
            run['event'] = event
            module.verify_run(run, SHA, 'linux-x86_64')

    def test_rejects_wrong_source_and_unfinished_or_failed_runs(self):
        for field, value in [('head_sha', 'b' * 40), ('status', 'in_progress'), ('conclusion', 'failure'),
                             ('conclusion', 'cancelled'), ('event', 'pull_request')]:
            with self.subTest(field=field, value=value):
                run = self.valid()
                run[field] = value
                with self.assertRaises(ValueError):
                    module.verify_run(run, SHA, 'linux-x86_64')

    def test_rejects_missing_failed_or_duplicate_native_job(self):
        for jobs in ([], [{'name': 'linux-x86_64', 'conclusion': 'failure'}],
                     [{'name': 'windows-x86_64', 'conclusion': 'success'}],
                     [{'name': 'linux-x86_64', 'conclusion': 'success'}] * 2):
            run = self.valid()
            run['jobs'] = jobs
            with self.assertRaises(ValueError):
                module.verify_run(run, SHA, 'linux-x86_64')


if __name__ == '__main__':
    unittest.main()
