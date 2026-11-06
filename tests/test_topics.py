import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))

from topics import topic_url, parse_topic_feed


def feed(items):
    body = ''.join(
        '<item><title>%s</title><link>%s</link><guid isPermaLink="false">%s</guid>'
        '<pubDate>Thu, 05 Nov 2026 10:00:00 GMT</pubDate>%s</item>' % (
            title, link, guid, source)
        for title, link, guid, source in items)
    return ('<?xml version="1.0"?><rss version="2.0"><channel><title>q - Google News</title>'
            + body + '</channel></rss>').encode()


class TopicUrlTests(unittest.TestCase):
    def test_query_is_encoded_and_scoped_to_english_us(self):
        url = topic_url('fusion energy')
        self.assertTrue(url.startswith('https://news.google.com/rss/search?q=fusion+energy'))
        self.assertIn('hl=en-US', url)
        self.assertIn('ceid=US:en', url)

    def test_blank_query_is_refused(self):
        with self.assertRaises(ValueError):
            topic_url('   ')

    def test_query_cannot_smuggle_extra_parameters(self):
        url = topic_url('a&hl=xx')
        self.assertNotIn('&hl=xx&', url)
        self.assertIn('a%26hl%3Dxx', url)


class ParseTopicTests(unittest.TestCase):
    def test_publisher_is_taken_from_the_source_tag(self):
        data = feed([('Bridge reopens - The Bugle', 'https://news.google.com/rss/articles/A1',
                      'A1', '<source url="https://bugle.example">The Bugle</source>')])
        item = parse_topic_feed(data)['items'][0]
        self.assertEqual(item['publisher'], 'The Bugle')
        self.assertEqual(item['title'], 'Bridge reopens')

    def test_publisher_falls_back_to_the_title_suffix(self):
        data = feed([('Markets steady - The Bugle', 'https://news.google.com/rss/articles/A2', 'A2', '')])
        item = parse_topic_feed(data)['items'][0]
        self.assertEqual(item['publisher'], 'The Bugle')
        self.assertEqual(item['title'], 'Markets steady')

    def test_title_without_a_suffix_keeps_its_dashes(self):
        data = feed([('MoofTCP - a replacement for MacTCP', 'https://news.google.com/rss/articles/A3', 'A3', '')])
        item = parse_topic_feed(data)['items'][0]
        self.assertEqual(item['title'], 'MoofTCP - a replacement for MacTCP')
        self.assertEqual(item['publisher'], '')

    def test_unsafe_and_duplicate_links_are_dropped(self):
        data = feed([
            ('One', 'javascript:alert(1)', 'A4', ''),
            ('Two', 'https://news.google.com/rss/articles/A5', 'A5', ''),
            ('Two again', 'https://news.google.com/rss/articles/A5', 'A5b', ''),
        ])
        items = parse_topic_feed(data)['items']
        self.assertEqual([i['title'] for i in items], ['Two'])

    def test_a_topic_body_is_recognised_as_a_feed(self):
        from discovery import looks_like_feed
        self.assertTrue(looks_like_feed(feed([('One', 'https://x.example/1', 'g', '')])))


if __name__ == '__main__':
    unittest.main()
