import { readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';
import { buildEdition, editionSummary, localIso, mergeArchive } from '../desktop/edition.js';

let code = readFileSync('desktop/plugin.js', 'utf8');
// Strip only real module imports: anchoring at line start keeps identifiers like importOpml intact.
code = code.replace(/^import\s[^\n]*\n/gm, '')
  .replace(/^export\s+/gm, '')
  .replace(/^default\s+\{/m, 'return {');
// Function components are invoked, so the tree the assertions walk is what the app would draw.
const jsx = (type, props) => (typeof type === 'function' ? type(props) : { type, props });
const useState = v => [typeof v === 'function' ? v() : v, () => {}];
const useEffect = () => {};
const ROUTES_AREA = 'routes', SIDEBAR_NAV_AREA = 'sidebar.nav', PALETTE_AREA = 'palette';

// A fresh module instance per test, so two different storage states do not share closures.
function makePlugin() {
  return new Function(
    'jsx', 'useState', 'useEffect', 'ROUTES_AREA', 'SIDEBAR_NAV_AREA', 'PALETTE_AREA',
    'buildEdition', 'editionSummary', 'mergeArchive', 'localIso', code
  )(jsx, useState, useEffect, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, buildEdition, editionSummary, mergeArchive, localIso);
}

const EMPTY_STORAGE = { get: (key, fallback) => (key === 'lastEdition' ? null : fallback), set: () => {} };

function render(plugin, storage) {
  const registrations = [];
  const ctx = { registerMany: entries => registrations.push(...entries), storage, rest: () => Promise.resolve({}), os: { openExternal: () => {} } };
  plugin.register(ctx);
  return { registrations, ctx, page: registrations[0].render() };
}

// 1. Registration surface and the empty state.
const plugin = makePlugin();
assert.equal(plugin.id, 'daily-edition');
assert.equal(plugin.defaultEnabled, false);
const empty = render(plugin, EMPTY_STORAGE);
const registrations = empty.registrations;
assert.equal(registrations.length, 4);
assert.equal(registrations[0].data.path, '/daily-edition');
assert.equal(registrations[0].area, ROUTES_AREA);
assert.equal(registrations[1].data.label, 'Daily Edition');
assert.equal(registrations[2].area, 'statusBar.right');
assert.equal(registrations[3].area, PALETTE_AREA);
assert.equal(typeof registrations[3].data.run, 'function');
assert.equal(typeof registrations[3].data.detail(), 'string');
assert.equal(empty.page.type, 'main');
const rendered = JSON.stringify(empty.page);
for (const text of [
  'Daily Edition', 'Print new edition', 'Add interest', 'Start from:', 'Find feed',
  'Import OPML', 'Export OPML', 'Preferences', 'Add an interest above',
  'Editorial voice'
]) {
  assert.ok(rendered.includes(text), `empty state is missing: ${text}`);
}

// 2. A paper that already exists is the first paint, not a blank page while fetching.
const fixture = buildEdition({
  sources: [
    { url: 'https://alpha.example/feed', source: 'Alpha', items: [
      { title: 'Fusion pilot plant breaks ground', url: 'https://alpha.example/1', snippet: 'Construction began.', date: 'Thu, 05 Nov 2026 08:00:00 GMT' },
      { title: 'Harbour fees rise in spring', url: 'https://alpha.example/2', snippet: 'Port authority confirmed.', date: 'Thu, 05 Nov 2026 07:00:00 GMT' }
    ] }
  ],
  now: '2026-11-05T12:00:00Z',
  watchwords: ['fusion']
});
const lastEdition = { ...fixture, standfirst: 'First edition. Everything here is new.' };
const stored = render(makePlugin(), {
  get: (key, fallback) => (key === 'lastEdition' ? lastEdition : fallback),
  set: () => {}
});
const withPaper = JSON.stringify(stored.page);
for (const text of [
  'Fusion pilot plant breaks ground', 'Harbour fees rise in spring',
  'Unread (2)', 'Saved (0)', 'j/k move', 'No. 1', 'search headlines'
]) {
  assert.ok(withPaper.includes(text), `composed edition is missing: ${text}`);
}
assert.ok(!withPaper.includes('Could not read'), 'first paint should not report a fetch error');

// 3. A saved story is listed in the Saved view without needing the edition to still carry it.
const savedRun = render(makePlugin(), {
  get: (key, fallback) => (key === 'lastEdition'
    ? lastEdition
    : key === 'saved'
      ? [{ url: 'https://old.example/9', title: 'An older saved story', snippet: 'Kept from a previous week.', sources: ['Alpha'], publishers: ['Alpha'] }]
      : key === 'read'
        ? ['https://alpha.example/1']
        : fallback),
  set: () => {}
});
const savedTree = JSON.stringify(savedRun.page);
assert.ok(savedTree.includes('Unread (1)'), 'read state should remove one story from unread');
assert.ok(savedTree.includes('Saved (1)'), 'saved state should be counted');

console.log('Desktop registration, empty state and composed-paper render passed');
