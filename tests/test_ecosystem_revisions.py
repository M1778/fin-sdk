import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = {'fin-auth', 'fin-websocket', 'fin-validate', 'template', 'zhttp', 'finson',
            'fin-crypto', 'fin-ssg', 'fin-kv', 'logg', 'xtest', 'Linf'}


def unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f'Duplicate revision entry: {name}')
        result[name] = value
    return result


class RevisionTests(unittest.TestCase):
    def test_inventory_is_exact_and_every_revision_is_immutable(self):
        pins = json.loads((ROOT / 'tests/ecosystem-revisions.json').read_text(encoding='utf-8'),
                          object_pairs_hook=unique_fields)
        self.assertEqual(set(pins), PROJECTS)
        for name, revision in pins.items():
            with self.subTest(project=name):
                self.assertIsInstance(revision, str)
                self.assertRegex(revision, r'^[0-9a-f]{40}$')

    def test_duplicate_revisions_are_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"zhttp":"a","zhttp":"b"}', object_pairs_hook=unique_fields)


if __name__ == '__main__':
    unittest.main()
