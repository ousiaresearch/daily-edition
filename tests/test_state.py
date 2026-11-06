import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import state


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {'HERMES_HOME': self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_when_nothing_is_saved(self):
        current = state.read()
        self.assertEqual(current['interests'], [])
        self.assertEqual(current['feeds'], [])
        self.assertEqual(current['archive'], [])

    def test_write_then_read_round_trip(self):
        state.write({'interests': ['fusion energy', 'housing in Málaga'], 'feeds': ['https://example.com/feed'],
                     'watchwords': ['Fusion'], 'persona': 'juno'})
        current = state.read()
        self.assertEqual(current['interests'], ['fusion energy', 'housing in Málaga'])
        self.assertEqual(current['watchwords'], ['fusion'])
        self.assertEqual(current['persona'], 'juno')

    def test_merges_instead_of_replacing(self):
        state.write({'interests': ['climate']})
        state.write({'feeds': ['https://example.com/feed']})
        current = state.read()
        self.assertEqual(current['interests'], ['climate'])
        self.assertEqual(current['feeds'], ['https://example.com/feed'])

    def test_caps_lists(self):
        state.write({'interests': ['interest %d' % i for i in range(100)]})
        self.assertEqual(len(state.read()['interests']), state.MAX_INTERESTS)

    def test_ignores_unknown_keys_and_bad_types(self):
        state.write({'evil': 'payload', 'interests': 'not a list', 'persona': 42})
        current = state.read()
        self.assertNotIn('evil', current)
        self.assertEqual(current['interests'], [])
        self.assertEqual(current['persona'], '')

    def test_file_is_private_and_valid_json(self):
        state.write({'interests': ['climate']})
        path = Path(self.tmp.name) / 'daily-edition' / 'state.json'
        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())['interests'], ['climate'])

    def test_corrupt_file_falls_back_to_defaults(self):
        path = Path(self.tmp.name) / 'daily-edition' / 'state.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not json')
        self.assertEqual(state.read()['interests'], [])

    def test_archive_entries_are_trimmed_to_known_keys(self):
        state.write({'archive': [{'number': 1, 'isoDate': '2026-11-05', 'printed': ['https://a', 'title'],
                                  'secret': 'drop me'}]})
        entry = state.read()['archive'][0]
        self.assertNotIn('secret', entry)
        self.assertEqual(entry['number'], 1)


if __name__ == '__main__':
    unittest.main()
