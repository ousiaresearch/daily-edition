import unittest
from unittest.mock import patch
from dashboard.plugin_api import read_feed

class ApiTests(unittest.TestCase):
    def test_errors_are_visible(self):
        with patch('dashboard.plugin_api.fetch_feed', side_effect=ValueError('bad feed')):
            self.assertEqual(read_feed('https://example.com'), {'error': 'bad feed'})
