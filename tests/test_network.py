import unittest
from dashboard.feed import checked_target

class NetworkTests(unittest.TestCase):
    def test_forbids_internal_and_credentials(self):
        for url in ['http://127.0.0.1/feed', 'http://localhost/a', 'file:///etc/passwd', 'https://user:pass@example.com/', 'http://[::1]/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                checked_target(url)

    def test_forbids_multicast(self):
        with self.assertRaises(ValueError):
            checked_target('http://224.0.0.1/feed')

    def test_allows_public_https(self):
        self.assertEqual(checked_target('https://8.8.8.8/feed')[0], '8.8.8.8')
