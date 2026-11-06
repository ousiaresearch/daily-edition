import unittest

from dashboard.discovery import build_opml, parse_opml


class OpmlExportTests(unittest.TestCase):
    def test_round_trips_through_the_parser(self):
        entries = [{'title': 'Alpha', 'url': 'https://alpha.example/feed'},
                   {'title': 'Beta & Co', 'url': 'https://beta.example/rss?x=1&y=2'}]
        document = build_opml(entries)
        self.assertIn('<opml version="2.0">', document)
        self.assertIn('Beta &amp; Co', document)
        parsed = parse_opml(document)
        self.assertEqual([feed['url'] for feed in parsed],
                         ['https://alpha.example/feed', 'https://beta.example/rss?x=1&y=2'])
        self.assertEqual(parsed[1]['title'], 'Beta & Co')

    def test_drops_unsafe_urls(self):
        document = build_opml([{'title': 'local', 'url': 'http://127.0.0.1/feed'},
                               {'title': 'file', 'url': 'file:///etc/passwd'},
                               {'title': 'ok', 'url': 'https://example.com/feed'}])
        parsed = parse_opml(document)
        self.assertEqual([feed['url'] for feed in parsed], ['https://example.com/feed'])

    def test_empty_list_is_still_a_document(self):
        parsed = parse_opml(build_opml([]))
        self.assertEqual(parsed, [])


if __name__ == '__main__':
    unittest.main()
