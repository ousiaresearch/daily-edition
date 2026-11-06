import unittest
from dashboard.feed import parse_feed

class FeedTests(unittest.TestCase):
    def test_rss_extracts_original_story(self):
        result = parse_feed(b"<rss><channel><title>Desk</title><item><title>News</title><link>https://example.com/story</link><description>Hello</description></item></channel></rss>", "https://example.com/feed")
        self.assertEqual(result["items"][0]["title"], "News")
        self.assertEqual(result["items"][0]["url"], "https://example.com/story")
        self.assertEqual(result["source"], "Desk")

    def test_atom_and_untrusted_markup(self):
        data = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Journal</title><entry><title>Item</title><link href="/story"/><summary type="html">&lt;b&gt;Hello&lt;/b&gt;</summary></entry></feed>'''
        item = parse_feed(data, 'https://example.com/feed')['items'][0]
        self.assertEqual((item['url'], item['snippet']), ('https://example.com/story', 'Hello'))

    def test_rejects_xml_entities(self):
        with self.assertRaises(ValueError):
            parse_feed(b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel><title>&x;</title></channel></rss>', 'https://example.com')
