import unittest

from dashboard.reader import extract

PAGE = b"""<!doctype html>
<html><head>
  <title>Council approves transit plan - Example News</title>
  <meta property="og:title" content="Council approves transit plan">
  <meta property="og:site_name" content="Example News">
  <meta name="author" content="A. Reporter">
  <link rel="canonical" href="/2026/transit-plan">
</head>
<body>
  <nav><a href="/">Home</a> <a href="/world">World</a></nav>
  <script>window.tracker = 'evil';</script>
  <style>.ad { color: red }</style>
  <article>
    <h1>Council approves transit plan</h1>
    <p>The city council voted on Tuesday to approve a transit plan that adds two bus corridors and a light rail spur to the airport.</p>
    <p>Subscribe to our newsletter for more coverage of local government and transport.</p>
    <h2>What changes</h2>
    <ul>
      <li>Two new bus corridors open in 2028.</li>
      <li>Fares stay flat for the first year of service.</li>
    </ul>
    <blockquote>This is the largest investment in transit in a generation, the mayor said.</blockquote>
    <p>Construction is expected to begin next spring, pending a final budget vote in March.</p>
  </article>
  <footer>All rights reserved. Privacy policy.</footer>
</body></html>"""


class ReaderTests(unittest.TestCase):
    def test_extracts_article_blocks_and_skips_chrome(self):
        article = extract(PAGE, 'https://example.com/2026/transit-plan')
        texts = [block['text'] for block in article['blocks']]
        joined = ' '.join(texts)
        self.assertEqual(article['title'], 'Council approves transit plan')
        self.assertEqual(article['site'], 'Example News')
        self.assertEqual(article['author'], 'A. Reporter')
        self.assertIn('two bus corridors', joined)
        self.assertIn('What changes', texts)
        self.assertTrue(any(block['type'] == 'li' for block in article['blocks']))
        self.assertTrue(any(block['type'] == 'quote' for block in article['blocks']))
        # Chrome, scripts and tracking never reach the block list.
        self.assertNotIn('evil', joined)
        self.assertNotIn('Privacy policy', joined)
        self.assertNotIn('Home World', joined)
        self.assertNotIn('Subscribe to our newsletter', joined)

    def test_rejects_a_page_without_prose(self):
        with self.assertRaisesRegex(ValueError, 'No article text'):
            extract('<html><body><nav>Menu</nav><script>x()</script></body></html>', 'https://example.com')

    def test_rejects_an_empty_page(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            extract('   ', 'https://example.com')

    def test_returns_no_html_markup(self):
        article = extract(PAGE, 'https://example.com/a')
        for block in article['blocks']:
            self.assertNotIn('<', block['text'])
            self.assertNotIn('>', block['text'])

    def test_reports_word_count_and_truncation_flag(self):
        article = extract(PAGE, 'https://example.com/a')
        self.assertGreater(article['words'], 20)
        self.assertFalse(article['truncated'])


if __name__ == '__main__':
    unittest.main()
