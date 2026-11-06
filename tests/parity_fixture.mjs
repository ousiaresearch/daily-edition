// Shared fixtures for the JS↔Python parity test: the same inputs through desktop/edition.js.
// tests/test_edition_parity.py runs this and compares the output with dashboard/edition.py.
import { buildEdition, editionDiff, editionSummary, mergeArchive, canonicalUrl } from '../desktop/edition.js';

const item = (title, url, snippet = '', date = '') => ({ title, url, snippet, date });
const sources = [
  { url: 'https://alpha.example/feed', source: 'Alpha', items: [
    item('City council votes on transit plan', 'https://alpha.example/1?utm_source=x', 'The council approved the plan.', 'Thu, 05 Nov 2026 09:00:00 GMT'),
    item('Fusion pilot plant breaks ground', 'https://alpha.example/2', 'Construction began this week.', 'Thu, 05 Nov 2026 08:00:00 GMT'),
    item('Harbour fees rise in spring', 'https://alpha.example/3', 'Port authority confirmed the change.', 'Thu, 05 Nov 2026 07:00:00 GMT')
  ] },
  { url: 'https://beta.example/feed', source: 'Beta', items: [
    item('Transit plan voted by city council', 'https://beta.example/9', 'A shorter summary.', 'Thu, 05 Nov 2026 10:00:00 GMT'),
    item('Weather warning for the coast', 'https://beta.example/8', 'Gales expected.', 'Thu, 05 Nov 2026 06:00:00 GMT')
  ] },
  { url: 'https://gamma.example/feed', source: 'Gamma', items: [
    item('Fusion pilot plant breaks ground', 'https://gamma.example/7', 'Ground was broken on Monday.', 'Thu, 05 Nov 2026 08:30:00 GMT'),
    item('Housing costs in Malaga climb again', 'https://gamma.example/6', 'Rents rose for a sixth quarter.', 'Thu, 05 Nov 2026 05:00:00 GMT')
  ] }
];

const now = '2026-11-05T12:00:00Z';
const first = buildEdition({ sources, now, watchwords: ['fusion'] });
const second = buildEdition({ sources, previous: first, now: '2026-11-06T12:00:00Z' });
const muted = buildEdition({ sources, now, muted: ['Beta'] });
const archive = mergeArchive([], editionSummary(first), 7);

const slim = edition => ({
  number: edition.number,
  isoDate: edition.isoDate,
  dateLabel: edition.dateLabel,
  storyCount: edition.storyCount,
  crossPosted: edition.crossPosted,
  withheld: edition.withheld,
  omitted: edition.omitted,
  mutedCount: edition.mutedCount,
  pinnedCount: edition.pinnedCount,
  sourceCount: edition.sourceCount,
  leadTitle: edition.lead ? edition.lead.title : '',
  leadPublishers: edition.lead ? edition.lead.publishers : [],
  stories: edition.stories.map(story => story.title),
  sections: edition.sections.map(section => [section.source, section.stories.map(story => story.title)]),
  printed: edition.printed
});

console.log(JSON.stringify({
  canonical: [
    canonicalUrl('https://Example.com/story/?utm_source=x&utm_medium=rss&id=7'),
    canonicalUrl('https://example.com/a/#section'),
    canonicalUrl('http://example.com:80/a'),
    canonicalUrl('not a url')
  ],
  first: slim(first),
  second: slim(second),
  muted: slim(muted),
  firstStandfirst: editionDiff(first, null).line,
  secondStandfirst: editionDiff(second, first).line,
  archiveLength: archive.length,
  archiveFirst: archive[0].isoDate
}, null, 1));
