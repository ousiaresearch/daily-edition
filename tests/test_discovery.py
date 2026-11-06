import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))

from discovery import extract_feed_links, parse_opml, looks_like_feed


class DiscoverTests(unittest.TestCase):
    def test_finds_rss_and_atom_alternates(self):
        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" title="Main" href="/feed.xml">
            <link rel='alternate' type='application/atom+xml' href='https://other.example/atom'>
            <link rel="stylesheet" href="/style.css">
        </head></html>'''
        found = extract_feed_links(html, 'https://site.example/blog/post')
        self.assertEqual(found, [
            {'url': 'https://site.example/feed.xml', 'title': 'Main'},
            {'url': 'https://other.example/atom', 'title': ''},
        ])

    def test_handles_attribute_order_case_and_json_feed(self):
        html = '''<LINK TYPE="application/feed+json" HREF="/feed.json" REL="alternate">
            <link href="/rss" type="application/rss+xml" rel="ALTERNATE">'''
        found = extract_feed_links(html, 'https://site.example/')
        self.assertEqual([f['url'] for f in found],
                         ['https://site.example/feed.json', 'https://site.example/rss'])

    def test_ignores_unsafe_or_relative_only_links_and_duplicates(self):
        html = '''<link rel="alternate" type="application/rss+xml" href="javascript:alert(1)">
            <link rel="alternate" type="application/rss+xml" href="//cdn.example/f.xml">
            <link rel="alternate" type="application/rss+xml" href="//cdn.example/f.xml">'''
        found = extract_feed_links(html, 'https://site.example/')
        self.assertEqual([f['url'] for f in found], ['https://cdn.example/f.xml'])

    def test_no_links_is_not_an_error(self):
        self.assertEqual(extract_feed_links('<html><body>hi</body></html>', 'https://x.example/'), [])

    def test_detects_a_feed_body(self):
        self.assertTrue(looks_like_feed(b'<?xml version="1.0"?><rss version="2.0"><channel/></rss>'))
        self.assertTrue(looks_like_feed(b'\n<feed xmlns="http://www.w3.org/2005/Atom"></feed>'))
        self.assertTrue(looks_like_feed(b'{"version": "https://jsonfeed.org/version/1.1"}'))
        self.assertFalse(looks_like_feed(b'<html><body>no</body></html>'))


class OpmlTests(unittest.TestCase):
    def test_reads_nested_outlines(self):
        opml = '''<?xml version="1.0"?>
        <opml version="2.0"><head><title>mine</title></head><body>
          <outline text="News">
            <outline type="rss" text="Alpha" title="Alpha Feed" xmlUrl="https://a.example/rss"/>
            <outline type="rss" text="Beta" xmlUrl="https://b.example/rss"/>
          </outline>
          <outline type="rss" text="Gamma" xmlUrl="https://c.example/atom.xml"/>
        </body></opml>'''
        feeds = parse_opml(opml)
        self.assertEqual([f['url'] for f in feeds],
                         ['https://a.example/rss', 'https://b.example/rss', 'https://c.example/atom.xml'])
        self.assertEqual(feeds[0]['title'], 'Alpha Feed')
        self.assertEqual(feeds[2]['title'], 'Gamma')

    def test_drops_unsafe_and_duplicate_subscriptions(self):
        opml = '''<opml version="1.0"><body>
          <outline text="Bad" xmlUrl="file:///etc/passwd"/>
          <outline text="Bad2" xmlUrl="ftp://a.example/f"/>
          <outline text="One" xmlUrl="https://a.example/rss"/>
          <outline text="One again" xmlUrl="https://a.example/rss"/>
        </body></opml>'''
        feeds = parse_opml(opml)
        self.assertEqual([f['url'] for f in feeds], ['https://a.example/rss'])

    def test_rejects_documents_that_are_not_opml(self):
        with self.assertRaises(ValueError):
            parse_opml('<rss version="2.0"><channel/></rss>')
        with self.assertRaises(ValueError):
            parse_opml('not xml at all')

    def test_rejects_entity_and_doctype_declarations(self):
        with self.assertRaises(ValueError):
            parse_opml('<!DOCTYPE opml [<!ENTITY x SYSTEM "file:///etc/passwd">]><opml><body/></opml>')


if __name__ == '__main__':
    unittest.main()
