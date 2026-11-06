"""Parity: the Python edition model must compose the same paper as desktop/edition.js.

The page composes in JS; the tool, `/edition` and cron compose in Python. Two implementations that
drift silently would be worse than one, so this test runs the JS against shared fixtures and
compares every field the reader or the tool can see.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

import dashboard.edition as model

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'tests' / 'parity_fixture.mjs'


def item(title, url, snippet='', date=''):
    return {'title': title, 'url': url, 'snippet': snippet, 'date': date}


SOURCES = [
    {'url': 'https://alpha.example/feed', 'source': 'Alpha', 'items': [
        item('City council votes on transit plan', 'https://alpha.example/1?utm_source=x',
             'The council approved the plan.', 'Thu, 05 Nov 2026 09:00:00 GMT'),
        item('Fusion pilot plant breaks ground', 'https://alpha.example/2',
             'Construction began this week.', 'Thu, 05 Nov 2026 08:00:00 GMT'),
        item('Harbour fees rise in spring', 'https://alpha.example/3',
             'Port authority confirmed the change.', 'Thu, 05 Nov 2026 07:00:00 GMT'),
    ]},
    {'url': 'https://beta.example/feed', 'source': 'Beta', 'items': [
        item('Transit plan voted by city council', 'https://beta.example/9',
             'A shorter summary.', 'Thu, 05 Nov 2026 10:00:00 GMT'),
        item('Weather warning for the coast', 'https://beta.example/8',
             'Gales expected.', 'Thu, 05 Nov 2026 06:00:00 GMT'),
    ]},
    {'url': 'https://gamma.example/feed', 'source': 'Gamma', 'items': [
        item('Fusion pilot plant breaks ground', 'https://gamma.example/7',
             'Ground was broken on Monday.', 'Thu, 05 Nov 2026 08:30:00 GMT'),
        item('Housing costs in Malaga climb again', 'https://gamma.example/6',
             'Rents rose for a sixth quarter.', 'Thu, 05 Nov 2026 05:00:00 GMT'),
    ]},
]


def slim(edition):
    return {
        'number': edition['number'],
        'isoDate': edition['isoDate'],
        'dateLabel': edition['dateLabel'],
        'storyCount': edition['storyCount'],
        'crossPosted': edition['crossPosted'],
        'withheld': edition['withheld'],
        'omitted': edition['omitted'],
        'mutedCount': edition['mutedCount'],
        'pinnedCount': edition['pinnedCount'],
        'sourceCount': edition['sourceCount'],
        'leadTitle': (edition['lead'] or {}).get('title', ''),
        'leadPublishers': (edition['lead'] or {}).get('publishers', []),
        'stories': [story['title'] for story in edition['stories']],
        'sections': [[section['source'], [story['title'] for story in section['stories']]]
                     for section in edition['sections']],
        'printed': edition['printed'],
    }


def run_node():
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('node is not installed')
    completed = subprocess.run([node, str(FIXTURE)], capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        raise AssertionError('node fixture failed: %s' % completed.stderr[-2000:])
    return json.loads(completed.stdout)


@unittest.skipUnless(FIXTURE.exists(), 'parity fixture missing')
class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = run_node()
        cls.first = model.build_edition(sources=SOURCES, now='2026-11-05T12:00:00Z',
                                        watchwords=['fusion'])
        cls.second = model.build_edition(sources=SOURCES, previous=cls.first,
                                         now='2026-11-06T12:00:00Z')
        cls.muted = model.build_edition(sources=SOURCES, now='2026-11-05T12:00:00Z', muted=['Beta'])

    def test_canonical_urls_match(self):
        self.assertEqual(self.js['canonical'], [
            model.canonical_url('https://Example.com/story/?utm_source=x&utm_medium=rss&id=7'),
            model.canonical_url('https://example.com/a/#section'),
            model.canonical_url('http://example.com:80/a'),
            model.canonical_url('not a url'),
        ])

    def test_first_edition_matches(self):
        self.assertEqual(self.js['first'], slim(self.first))

    def test_second_edition_matches(self):
        self.assertEqual(self.js['second'], slim(self.second))

    def test_muting_matches(self):
        self.assertEqual(self.js['muted'], slim(self.muted))

    def test_standfirst_matches(self):
        self.assertEqual(self.js['firstStandfirst'], model.edition_diff(self.first, None)['line'])
        self.assertEqual(self.js['secondStandfirst'], model.edition_diff(self.second, self.first)['line'])

    def test_same_event_rule_matches(self):
        def filing(title, url, publisher):
            return {'title': title, 'url': url, 'publishers': [publisher], 'sources': [publisher]}

        cases = [
            (('City council approves transit plan after two-year fight', 'https://alpha.example/1', 'Alpha'),
             ('Transit plan clears council in 7-4 vote', 'https://beta.example/2', 'Beta')),
            (('Transit plan approved by council', 'https://alpha.example/1', 'Alpha'),
             ('Transit plan delayed by council', 'https://beta.example/2', 'Beta')),
            (('Harbour fees rise in 2025', 'https://alpha.example/1', 'Alpha'),
             ('Harbour fees rise in 2026', 'https://beta.example/2', 'Beta')),
            (('Transit plan clears council', 'https://alpha.example/1', 'Alpha'),
             ('Transit plan vote scheduled', 'https://alpha.example/2', 'Alpha')),
            (('Fusion plant breaks ground', 'https://alpha.example/1', 'Alpha'),
             ('Fusion plant breaks ground', 'https://beta.example/2', 'Beta')),
        ]
        ours = [model.same_story(filing(*left), filing(*right)) for left, right in cases]
        self.assertEqual(self.js['pairs'], ours)

    def test_duplicate_story_is_clustered_identically(self):
        duplicate = model.build_edition(sources=[
            {'url': 'https://alpha.example/feed', 'source': 'Alpha', 'items': [
                item('City council approves transit plan after two-year fight', 'https://alpha.example/1')]},
            {'url': 'https://beta.example/feed', 'source': 'Beta', 'items': [
                item('Transit plan clears council in 7-4 vote', 'https://beta.example/2')]},
        ], now='2026-11-05T12:00:00Z')
        self.assertEqual(self.js['duplicate'], slim(duplicate))

    def test_archive_summary_matches(self):
        summary = model.edition_summary(self.first)
        merged = model.merge_archive([], summary, 7)
        self.assertEqual(self.js['archiveLength'], len(merged))
        self.assertEqual(self.js['archiveFirst'], merged[0]['isoDate'])


if __name__ == '__main__':
    unittest.main()
