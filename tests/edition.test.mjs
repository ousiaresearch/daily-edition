// Unit tests for the edition model: clustering, de-duplication, sections, archive numbering.
// Run: node --test tests/edition.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canonicalUrl, titleKey, similarity, buildEdition, editionDiff, mergeArchive, editionSummary } from '../desktop/edition.js';

const item = (title, url, snippet = '', date = '') => ({ title, url, snippet, date });

test('canonicalUrl strips tracking params and trailing slash', () => {
  assert.equal(
    canonicalUrl('https://Example.com/story/?utm_source=x&utm_medium=rss&id=7'),
    'https://example.com/story?id=7'
  );
  assert.equal(canonicalUrl('https://example.com/a#section'), 'https://example.com/a');
});

test('titleKey ignores case, punctuation and stopwords', () => {
  assert.equal(titleKey('The City Council, Votes — Again!'), 'city council votes again');
});

test('similarity scores overlapping headlines', () => {
  assert.ok(similarity('City council votes on transit plan', 'Transit plan voted by city council') > 0.8);
  assert.equal(similarity('City council votes', 'New phone released today'), 0);
});

test('clusters the same story reported by two sources into one story', () => {
  const edition = buildEdition({
    sources: [
      { url: 'https://a.example/feed', source: 'Alpha', items: [item('City council votes on transit plan', 'https://a.example/1')] },
      { url: 'https://b.example/feed', source: 'Beta', items: [item('Transit plan voted by city council', 'https://b.example/2')] }
    ],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.stories.length, 1);
  assert.deepEqual(edition.stories[0].sources.sort(), ['Alpha', 'Beta']);
  assert.equal(edition.lead.title.length > 0, true);
  assert.equal(edition.crossPosted, 1);
});

test('identical links from two feeds cluster even when titles differ', () => {
  const edition = buildEdition({
    sources: [
      { url: 'https://a.example/feed', source: 'Alpha', items: [item('Markets steady', 'https://news.example/x?utm_source=a')] },
      { url: 'https://b.example/feed', source: 'Beta', items: [item('Stocks hold as traders wait', 'https://news.example/x')] }
    ],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.stories.length, 1);
  assert.equal(edition.stories[0].sources.length, 2);
});

test('stories already carried in a previous edition are excluded', () => {
  const previous = { number: 3, printed: ['https://a.example/1', 'city council votes on transit plan'] };
  const edition = buildEdition({
    sources: [
      { url: 'https://a.example/feed', source: 'Alpha', items: [
        item('City council votes on transit plan', 'https://a.example/1'),
        item('Bridge reopens ahead of schedule', 'https://a.example/2')
      ] }
    ],
    previous,
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.stories.length, 1);
  assert.equal(edition.stories[0].title, 'Bridge reopens ahead of schedule');
  assert.equal(edition.withheld, 1);
  assert.equal(edition.number, 4);
});

test('sections group by source and omit the lead', () => {
  const edition = buildEdition({
    sources: [
      { url: 'https://a.example/feed', source: 'Alpha', items: [
        item('City council votes on transit plan', 'https://a.example/1'),
        item('Markets steady', 'https://a.example/2')
      ] },
      { url: 'https://b.example/feed', source: 'Beta', items: [item('Transit plan voted by city council', 'https://b.example/3')] }
    ],
    now: '2026-11-05T12:00:00Z'
  });
  // The two consensus headlines become the lead (2 sources beats 1).
  assert.equal(edition.lead.sources.length, 2);
  const sectioned = edition.sections.flatMap(s => s.stories.map(x => x.url));
  assert.ok(!sectioned.includes(edition.lead.url));
  assert.equal(edition.sections.length, 1);
  assert.equal(edition.sections[0].source, 'Alpha');
});

test('empty input produces a valid, printable edition', () => {
  const edition = buildEdition({ sources: [], now: '2026-11-05T12:00:00Z' });
  assert.equal(edition.stories.length, 0);
  assert.equal(edition.lead, null);
  assert.deepEqual(edition.sections, []);
  assert.equal(edition.number, 1);
  assert.match(edition.dateLabel, /November/);
});

test('maxStories caps the printed edition', () => {
  const items = Array.from({ length: 30 }, (_, i) => item('Story number ' + i, 'https://a.example/' + i));
  const edition = buildEdition({ sources: [{ url: 'u', source: 'Alpha', items }], now: '2026-11-05T12:00:00Z' });
  assert.equal(edition.stories.length, 20);
  assert.equal(edition.omitted, 10);
});

test('mergeArchive keeps dated editions newest-first and bounded', () => {
  const make = n => ({ number: n, dateLabel: 'November ' + n, isoDate: '2026-11-' + String(n).padStart(2, '0') });
  let archive = [];
  for (let n = 1; n <= 12; n += 1) archive = mergeArchive(archive, make(n), 5);
  assert.equal(archive.length, 5);
  assert.equal(archive[0].number, 12);
  assert.equal(archive[4].number, 8);
  // Re-running the same edition replaces it rather than duplicating.
  archive = mergeArchive(archive, make(12), 5);
  assert.equal(archive.filter(e => e.number === 12).length, 1);
});

test('an archived summary keeps the keys needed to withhold repeats tomorrow', () => {
  const built = buildEdition({
    sources: [{ url: 'u', source: 'Alpha', items: [item('Bridge reopens ahead of schedule', 'https://a.example/2?utm_source=rss')] }],
    now: '2026-11-05T12:00:00Z'
  });
  const summary = editionSummary(built);
  assert.ok(summary.printed.includes('https://a.example/2'));
  assert.equal(summary.isoDate, '2026-11-05');
  assert.equal(summary.leadTitle, 'Bridge reopens ahead of schedule');
  // The persisted card is small: no full article bodies are kept.
  assert.ok(JSON.stringify(summary).length < 4000);

  // Tomorrow, the same story arriving again is withheld rather than reprinted.
  const tomorrow = buildEdition({
    sources: [{ url: 'u', source: 'Beta', items: [item('Bridge reopens ahead of schedule', 'https://b.example/mirror')] }],
    previous: summary,
    now: '2026-11-06T12:00:00Z'
  });
  assert.equal(tomorrow.storyCount, 0);
  assert.equal(tomorrow.withheld, 1);
  assert.equal(tomorrow.number, 2);
});

test('the edition is dated in the reader\'s local day, not UTC', () => {
  // 23:30 local is already "tomorrow" in UTC for most of the Americas.
  const lateEvening = new Date(2026, 10, 5, 23, 30);
  const edition = buildEdition({
    sources: [{ url: 'u', source: 'Alpha', items: [item('Late filing', 'https://a.example/late')] }],
    now: lateEvening
  });
  assert.equal(edition.isoDate, '2026-11-05');
  assert.match(edition.dateLabel, /5 November 2026/);
  assert.equal(edition.builtAt, lateEvening.toISOString());
});

test('muted sources are dropped from the edition entirely', () => {
  const edition = buildEdition({
    sources: [
      { url: 'a', source: 'Alpha', items: [item('Bridge reopens ahead of schedule', 'https://a.example/1')] },
      { url: 'b', source: 'Beta', items: [item('Markets steady after a quiet session', 'https://b.example/2')] }
    ],
    muted: ['Beta'],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.storyCount, 1);
  assert.equal(edition.lead.title, 'Bridge reopens ahead of schedule');
  assert.deepEqual(edition.sections, []);
  assert.equal(edition.mutedCount, 1);
});

test('muting one outlet neither credits it nor turns one filing into consensus', () => {
  const edition = buildEdition({
    sources: [
      { url: 'a', source: 'Alpha', items: [item('Shared headline about the harbour', 'https://a.example/1')] },
      { url: 'b', source: 'Beta', items: [item('Shared headline about the harbour', 'https://b.example/2')] },
      { url: 'c', source: 'Gamma', items: [item('Something else entirely today', 'https://c.example/3')] }
    ],
    muted: ['Beta'],
    now: '2026-11-05T12:00:00Z'
  });
  // Beta is muted, so the remaining filing is single-source: it stays on the page, but the
  // page must not claim the story was cross-posted.
  assert.equal(edition.storyCount, 2);
  const shared = edition.stories.find(s => /harbour/.test(s.title));
  assert.deepEqual(shared.sources, ['Alpha']);
  assert.equal(edition.crossPosted, 0);
});

test('watchwords mark and promote matching stories', () => {
  const edition = buildEdition({
    sources: [{ url: 'a', source: 'Alpha', items: [
      item('Bridge reopens ahead of schedule', 'https://a.example/1', '', 'Thu, 05 Nov 2026 10:00:00 GMT'),
      item('Fusion pilot plant clears safety review', 'https://a.example/2', '', 'Thu, 05 Nov 2026 08:00:00 GMT')
    ] }],
    watchwords: ['fusion'],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.stories[0].title, 'Fusion pilot plant clears safety review');
  assert.equal(edition.stories[0].pinned, true);
  assert.equal(edition.pinnedCount, 1);
  assert.equal(edition.lead.pinned, true);
});

test('consensus counts publishers, not the number of interests that surfaced a story', () => {
  const shared = 'Harbour board approves the new ferry terminal';
  const edition = buildEdition({
    sources: [
      { url: 'interest:ferries', source: 'ferries', items: [{ title: shared, url: 'https://g.example/a1', publisher: 'The Bugle' }] },
      { url: 'interest:ports', source: 'ports', items: [{ title: shared, url: 'https://g.example/a1', publisher: 'The Bugle' }] }
    ],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.storyCount, 1);
  assert.equal(edition.crossPosted, 0);
  assert.deepEqual(edition.lead.publishers, ['The Bugle']);
});

test('the same story from two mastheads is cross-posted and credits both', () => {
  const edition = buildEdition({
    sources: [
      { url: 'interest:ferries', source: 'ferries', items: [{ title: 'Harbour board approves the new ferry terminal', url: 'https://a.example/1', publisher: 'The Bugle' }] },
      { url: 'interest:ports', source: 'ports', items: [{ title: 'Ferry terminal approved by harbour board', url: 'https://b.example/2', publisher: 'The Herald' }] }
    ],
    now: '2026-11-05T12:00:00Z'
  });
  assert.equal(edition.storyCount, 1);
  assert.equal(edition.crossPosted, 1);
  assert.deepEqual(edition.lead.publishers.sort(), ['The Bugle', 'The Herald']);
  assert.deepEqual(edition.lead.sources.sort(), ['ferries', 'ports']);
});

test('the standfirst says what changed since the last edition', () => {
  const previous = {
    number: 4,
    isoDate: '2026-11-04',
    printed: ['https://a.example/1', 'city council votes on transit plan', 'https://a.example/2', 'bridge reopened'],
    headlines: []
  };
  const edition = buildEdition({
    sources: [{ url: 'u', source: 'Alpha', items: [
      item('City council votes on transit plan', 'https://a.example/1'),   // repeat -> withheld
      item('Ferry terminal approved', 'https://a.example/3')               // new
    ] }],
    previous,
    now: '2026-11-05T12:00:00Z'
  });
  const diff = editionDiff(edition, previous);
  assert.equal(diff.first, false);
  assert.equal(diff.fresh, 1);
  assert.equal(diff.carried, 1);
  assert.equal(diff.dropped, 1);       // the bridge story did not come back
  assert.match(diff.line, /1 new since No\. 4/);
  assert.match(diff.line, /1 still running/);
  assert.match(diff.line, /1 gone from your feeds/);
});

test('a first edition has a standfirst that says nothing changed yet', () => {
  const edition = buildEdition({
    sources: [{ url: 'u', source: 'Alpha', items: [item('Something happened today', 'https://a.example/9')] }],
    now: '2026-11-05T12:00:00Z'
  });
  const diff = editionDiff(edition, null);
  assert.equal(diff.first, true);
  assert.match(diff.line, /First edition/);
});
