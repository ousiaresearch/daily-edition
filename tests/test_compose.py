import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import dashboard.compose as compose

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)

STATE = {
    'interests': ['fusion energy'],
    'feeds': ['https://alpha.example/feed'],
    'muted': [],
    'watchwords': ['fusion'],
    'archive': [],
}

TOPIC = {'source': 'Fusion energy', 'items': [
    {'title': 'Fusion pilot plant breaks ground', 'url': 'https://alpha.example/1',
     'snippet': 'Construction began this week.', 'date': 'Thu, 05 Nov 2026 08:00:00 GMT'},
    {'title': 'Fusion funding round closes', 'url': 'https://alpha.example/2',
     'snippet': 'Investors committed new capital.', 'date': 'Thu, 05 Nov 2026 07:00:00 GMT'},
]}

FEED = {'source': 'Alpha', 'items': [
    {'title': 'Harbour fees rise in spring', 'url': 'https://alpha.example/3',
     'snippet': 'Port authority confirmed the change.', 'date': 'Thu, 05 Nov 2026 06:00:00 GMT'},
]}


class ComposeTests(unittest.TestCase):
    def run_compose(self, state=STATE, topic=TOPIC, feed=FEED, **kwargs):
        with patch.object(compose._feed, 'fetch_topic', return_value=topic), \
             patch.object(compose._feed, 'fetch_feed', return_value=feed):
            return compose.compose_and_render(state, now=NOW, **kwargs)

    def test_prints_a_dated_front_page(self):
        result = self.run_compose()
        text = result['text']
        self.assertIn('DAILY EDITION — No. 1 — Thursday, 5 November 2026', text)
        self.assertIn('Fusion pilot plant breaks ground', text)
        self.assertIn('Harbour fees rise in spring', text)
        self.assertIn('https://alpha.example/1', text)
        self.assertEqual(result['errors'], [])

    def test_watchwords_pin_a_story_to_the_lead(self):
        result = self.run_compose()
        self.assertIn('★ Fusion funding round closes', result['text'])
        self.assertEqual(result['edition']['pinnedCount'], 2)
        self.assertEqual(result['edition']['lead']['title'], 'Fusion pilot plant breaks ground')

    def test_a_failing_source_is_reported_not_fatal(self):
        with patch.object(compose._feed, 'fetch_topic', side_effect=ValueError('HTTP 429')), \
             patch.object(compose._feed, 'fetch_feed', return_value=FEED):
            result = compose.compose_and_render(STATE, now=NOW)
        self.assertEqual(result['edition']['storyCount'], 1)
        self.assertTrue(any('HTTP 429' in error for error in result['errors']))
        self.assertIn('Sources that could not be read', result['text'])

    def test_no_sources_yields_an_honest_empty_page(self):
        result = compose.compose_and_render({'interests': [], 'feeds': []}, now=NOW)
        self.assertEqual(result['edition']['storyCount'], 0)
        self.assertIn('DAILY EDITION', result['text'])

    def test_a_second_printing_withholds_what_already_ran(self):
        first = self.run_compose()
        archived = dict(STATE, archive=[compose.edition_summary(first['edition'])])
        tomorrow = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
        with patch.object(compose._feed, 'fetch_topic', return_value=TOPIC), \
             patch.object(compose._feed, 'fetch_feed', return_value=FEED):
            second = compose.compose_and_render(archived, now=tomorrow)
        self.assertEqual(second['edition']['withheld'], 3)
        self.assertEqual(second['edition']['storyCount'], 0)
        self.assertEqual(second['edition']['number'], 2)


if __name__ == '__main__':
    unittest.main()
