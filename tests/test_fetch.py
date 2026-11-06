import unittest
from unittest.mock import patch

from dashboard.feed import fetch_feed, MAX_REDIRECTS

RULE = '<rss version="2.0"><channel><title>Example</title><item><title>A story</title><link>https://example.com/a</link></item></channel></rss>'


class Response:
    def __init__(self, status, body=b'', headers=None):
        self.status = status
        self._body = body
        self._headers = headers or []

    def read(self, n):
        return self._body[:n]

    def getheaders(self):
        return self._headers


class Connection:
    """Serves the scripted responses in order; every request is recorded."""
    script = []
    calls = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port

    def request(self, method, path, headers=None):
        Connection.calls.append((self.host, path))

    def getresponse(self):
        return Connection.script.pop(0)

    def close(self):
        pass


def fake_target(url):
    # Every hop is vetted by checked_target; the fake accepts public hosts and refuses the
    # private address a hostile redirect would point at.
    if 'internal' in url or '169.254' in url:
        raise ValueError('Feed address is not public')
    return '93.184.216.34', 443


class RedirectTests(unittest.TestCase):
    def setUp(self):
        Connection.script = []
        Connection.calls = []

    def run_with(self, script):
        Connection.script = list(script)
        with patch('dashboard.feed.checked_target', side_effect=fake_target), \
             patch('http.client.HTTPSConnection', Connection):
            return fetch_feed('https://example.com/feed')

    def test_follows_a_redirect_to_a_public_host(self):
        result = self.run_with([
            Response(301, headers=[('Location', 'https://moved.example/rss')]),
            Response(200, RULE.encode()),
        ])
        self.assertEqual(result['source'], 'Example')
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(Connection.calls[0][0], 'example.com')

    def test_refuses_a_redirect_to_a_private_host(self):
        with self.assertRaisesRegex(ValueError, 'not public'):
            self.run_with([Response(302, headers=[('Location', 'https://internal.example/feed')])])

    def test_gives_up_after_the_hop_limit(self):
        chain = [Response(302, headers=[('Location', 'https://example.com/again')])] * (MAX_REDIRECTS + 1)
        with self.assertRaisesRegex(ValueError, 'Too many redirects'):
            self.run_with(chain + [Response(200, RULE.encode())])

    def test_relative_location_is_resolved(self):
        self.run_with([
            Response(307, headers=[('Location', '/rss.xml')]),
            Response(200, RULE.encode()),
        ])
        self.assertEqual(Connection.calls[1][1], '/rss.xml')

    def test_a_redirect_without_location_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'without a Location'):
            self.run_with([Response(302)])
