// Edition model: turns a set of fetched feeds into a dated front page.
//
// The unit here is an *edition*, not a feed: one composed front page with a lead story,
// sections, cross-source consensus and a printed record, so the same story arriving from
// three outlets reads once, and a later refresh does not reprint yesterday's news.
// Pure functions only — no DOM, no network — so it is unit-testable.

const TRACKING = /^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$|source$|igshid$)/i;

const STOPWORDS = new Set([
  'a', 'an', 'and', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'is', 'it', 'its', 'of', 'on',
  'or', 'that', 'the', 'to', 'was', 'were', 'will', 'with', 'after', 'before', 'over', 'under',
  'this', 'these', 'those', 'has', 'have', 'had', 'not', 'but', 'are', 'am', 'been', 'into'
]);

export function canonicalUrl(raw) {
  let url;
  try {
    url = new URL(String(raw || '').trim());
  } catch {
    return '';
  }
  if (!['http:', 'https:'].includes(url.protocol)) return '';
  url.hash = '';
  url.hostname = url.hostname.toLowerCase();
  for (const key of [...url.searchParams.keys()]) {
    if (TRACKING.test(key)) url.searchParams.delete(key);
  }
  let path = url.pathname.replace(/\/+$/, '');
  if (!path) path = '/';
  const query = url.searchParams.toString();
  return `${url.protocol}//${url.host}${path}${query ? '?' + query : ''}`;
}

export function titleKey(title) {
  return String(title || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(token => token && !STOPWORDS.has(token))
    .join(' ');
}

const stem = word => (word.length > 4
  ? word.replace(/(ing|ed|es|s)$/, '').replace(/([^aeiou])\1$/, '$1')
  : word);

const tokens = title => new Set(titleKey(title).split(' ').filter(Boolean).map(stem));

export function similarity(a, b) {
  const left = tokens(a);
  const right = tokens(b);
  if (!left.size || !right.size) return 0;
  let shared = 0;
  for (const token of left) if (right.has(token)) shared += 1;
  return shared / (left.size + right.size - shared);
}

function timestamp(value) {
  const parsed = Date.parse(String(value || ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function dateLabel(date) {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  }).format(date);
}

// The edition is dated by the reader's own day: a paper printed at 23:30 local is today's paper,
// even though UTC has already rolled over.
export function localIso(date) {
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// One story, once. Two headlines are the same story when they share the same named thing and the
// same kind of action ("council approves transit plan" / "transit plan clears council vote"), or
// when their wording overlaps enough. Word order, verb choice and length must not matter; a
// different year or a conflicting action ("approved" vs "delayed") must.
const ACTION_FAMILY = {
  approve: 'decide', approves: 'decide', approved: 'decide', approve: 'decide',
  pass: 'decide', passes: 'decide', passed: 'decide', adopt: 'decide', adopts: 'decide', adopted: 'decide',
  vote: 'decide', votes: 'decide', voted: 'decide', clear: 'decide', clears: 'decide', cleared: 'decide',
  back: 'decide', backs: 'decide', backed: 'decide', decide: 'decide', decides: 'decide', decided: 'decide',
  reject: 'refuse', rejects: 'refuse', rejected: 'refuse', block: 'refuse', blocks: 'refuse', blocked: 'refuse',
  veto: 'refuse', vetoes: 'refuse', vetoed: 'refuse', deny: 'refuse', denies: 'refuse', denied: 'refuse',
  delay: 'delay', delays: 'delay', delayed: 'delay', postpone: 'delay', postponed: 'delay',
  shelve: 'delay', shelved: 'delay', suspend: 'delay', suspended: 'delay',
  rise: 'up', rises: 'up', rising: 'up', climb: 'up', climbs: 'up', climbed: 'up',
  increase: 'up', increases: 'up', soar: 'up', soars: 'up', gain: 'up', gains: 'up',
  fall: 'down', falls: 'down', fell: 'down', drop: 'down', drops: 'down', dropped: 'down',
  decline: 'down', declines: 'down', cut: 'down', cuts: 'down', plunge: 'down', plunges: 'down',
  launch: 'begin', launches: 'begin', launched: 'begin', unveil: 'begin', unveils: 'begin',
  open: 'begin', opens: 'begin', opened: 'begin', release: 'begin', releases: 'begin', start: 'begin', starts: 'begin',
  close: 'end', closes: 'end', closed: 'end', shut: 'end', shuts: 'end', halt: 'end', halts: 'end',
  warn: 'warn', warns: 'warn', warned: 'warn', warning: 'warn', alert: 'warn', alerts: 'warn',
};

const actionFamilies = title => new Set(
  titleKey(title).split(' ').map(word => ACTION_FAMILY[word]).filter(Boolean)
);

const yearsIn = title => new Set((String(title || '').match(/\b(19|20)\d{2}\b/g) || []));

// Both headlines carry a year and they disagree: different filings, not one story.
const conflictingYears = (a, b) => {
  const left = yearsIn(a);
  const right = yearsIn(b);
  if (!left.size || !right.size) return false;
  for (const year of left) if (right.has(year)) return false;
  return true;
};

const compatibleActions = (a, b) => {
  const left = actionFamilies(a);
  const right = actionFamilies(b);
  if (!left.size || !right.size) return true;
  for (const family of left) if (right.has(family)) return true;
  return false;
};

// "transit plan" is the named thing; a shared bigram is a strong signal that two wordings are one
// event, provided the actions do not contradict each other.
const contentBigrams = title => {
  const words = titleKey(title).split(' ').filter(word => word.length >= 4);
  const out = new Set();
  for (let i = 0; i + 1 < words.length; i += 1) out.add(words[i] + ' ' + words[i + 1]);
  return out;
};

const sharesBigram = (a, b) => {
  const right = contentBigrams(b);
  for (const gram of contentBigrams(a)) if (right.has(gram)) return true;
  return false;
};

export function sameStory(a, b) {
  if (a.url && b.url && a.url === b.url) return true;
  if (conflictingYears(a.title, b.title)) return false;
  // A contradiction in the verb is decisive: "approved" and "delayed" are never one story, however
  // much of the rest of the headline they share.
  if (!compatibleActions(a.title, b.title)) return false;
  const left = tokens(a.title);
  const right = tokens(b.title);
  const shared = [...left].filter(token => right.has(token)).length;
  const minSize = Math.min(left.size, right.size);
  if (!shared || !minSize) return false;
  const containment = shared / minSize;
  const jaccard = shared / (left.size + right.size - shared);
  const score = 0.65 * containment + 0.35 * jaccard;
  if (score >= 0.66 && shared >= 3) return true;

  const publishersA = a.publishers || [];
  const publishersB = b.publishers || [];
  const fromDifferentOutlets = !publishersA.some(name => publishersB.includes(name));
  if (!fromDifferentOutlets) return false;   // a masthead does not cross-post itself
  if (shared >= 2 && sharesBigram(a.title, b.title)) return true;
  return containment >= 0.9 && minSize >= 3;
}

// Group items that are the same story: identical canonical link first, then headline evidence.
// Union-find, so A~B and B~C collapses A, B and C into one filing.
function cluster(sources) {
  const items = [];
  for (const feed of sources) {
    for (const raw of (feed.items || [])) {
      const url = canonicalUrl(raw.url);
      const title = String(raw.title || '').trim();
      if (!url || !title) continue;
      items.push({
        title, url,
        snippet: String(raw.snippet || ''),
        date: String(raw.date || ''),
        at: timestamp(raw.date),
        sources: [feed.source],
        // Who filed it, as distinct from which interest surfaced it. Falls back to the feed name
        // so plain subscriptions keep working unchanged.
        publishers: [String(raw.publisher || feed.source)],
        also: [{ source: feed.source, url }]
      });
    }
  }
  const parent = items.map((item, index) => index);
  const find = index => {
    let root = index;
    while (parent[root] !== root) root = parent[root];
    while (parent[index] !== root) { const next = parent[index]; parent[index] = root; index = next; }
    return root;
  };
  const union = (a, b) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[Math.max(rootA, rootB)] = Math.min(rootA, rootB);
  };
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      if (sameStory(items[i], items[j])) union(i, j);
    }
  }
  const groups = new Map();
  items.forEach((item, index) => {
    const root = find(index);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(item);
  });
  return [...groups.values()].map(group => {
    const story = { ...group[0], sources: [...group[0].sources], publishers: [...group[0].publishers], also: [...group[0].also] };
    for (const item of group.slice(1)) {
      for (const source of item.sources) if (!story.sources.includes(source)) story.sources.push(source);
      for (const publisher of item.publishers) if (!story.publishers.includes(publisher)) story.publishers.push(publisher);
      for (const entry of item.also) if (!story.also.some(known => known.url === entry.url)) story.also.push(entry);
      if (item.snippet.length > story.snippet.length) story.snippet = item.snippet;
      if (item.at && (!story.at || item.at < story.at)) {
        story.at = item.at;
        story.date = item.date;
      }
    }
    return story;
  });
}

function rank(stories, order) {
  return stories
    .map((story, index) => ({ story, index }))
    .sort((a, b) => (Number(b.story.pinned) - Number(a.story.pinned))
      || (b.story.publishers.length - a.story.publishers.length)
      || (b.story.at - a.story.at)
      || (a.index - b.index))
    .map(entry => entry.story)
    .map(story => { order.push(story); return story; });
}

// A watchword promotes stories the reader has declared an interest in. Matching is on word
// stems, so "fusion" also catches "fusion's" and "fusions", but not "profusion".
function matchesWatchword(story, watchwords) {
  const words = (watchwords || []).map(word => stem(String(word).toLowerCase())).filter(Boolean);
  if (!words.length) return false;
  const haystack = new Set([...tokens(story.title), ...tokens(story.snippet || '')]);
  return words.some(word => haystack.has(word));
}

export function buildEdition({ sources = [], previous = null, now = new Date(), maxStories = 20, muted = [], watchwords = [] } = {}) {
  const built = now instanceof Date ? now : new Date(now);
  const isoDate = localIso(built);
  const withheldKeys = new Set((previous && previous.printed) || []);

  // Muted outlets contribute nothing: no stories, no byline, no consensus credit.
  const mutedSet = new Set((muted || []).map(name => String(name).toLowerCase()));
  const active = sources.filter(feed => !mutedSet.has(String(feed.source || '').toLowerCase()));
  const mutedCount = sources.filter(feed => mutedSet.has(String(feed.source || '').toLowerCase())).length;

  const all = cluster(active).map(story => ({
    ...story,
    pinned: matchesWatchword(story, watchwords)
  }));
  const fresh = [];
  const withheldStories = [];
  let withheld = 0;
  for (const story of all) {
    if (withheldKeys.has(story.url) || withheldKeys.has(titleKey(story.title))) {
      withheld += 1;
      withheldStories.push(story);
      continue;
    }
    fresh.push(story);
  }

  const ordered = rank(fresh, []);
  const printed = ordered.slice(0, maxStories);
  const omitted = ordered.length - printed.length;
  const lead = printed[0] || null;
  const remainder = printed.slice(1);

  const sections = [];
  for (const story of remainder) {
    const source = story.sources[0];
    let section = sections.find(entry => entry.source === source);
    if (!section) {
      section = { source, stories: [] };
      sections.push(section);
    }
    section.stories.push(story);
  }

  const crossPosted = printed.filter(story => story.publishers.length > 1).length;

  return {
    number: ((previous && previous.number) || 0) + 1,
    isoDate,
    dateLabel: dateLabel(built),
    builtAt: built.toISOString(),
    lead,
    sections,
    stories: printed,
    printed: printed.flatMap(story => [story.url, titleKey(story.title)]).filter(Boolean),
    // The same keys kept per story, so a "drop" is counted per story rather than per key.
    printedStories: printed.map(story => [story.url, titleKey(story.title)]),
    // Everything that came back this time, printed or withheld: what a drop is measured against.
    returned: printed.concat(withheldStories).flatMap(story => [story.url, titleKey(story.title)]).filter(Boolean),
    withheld,
    omitted,
    crossPosted,
    mutedCount,
    pinnedCount: printed.filter(story => story.pinned).length,
    sourceCount: sources.filter(feed => (feed.items || []).length).length,
    storyCount: printed.length
  };
}

// Newest-first, one entry per calendar day, bounded, and re-running a refresh for the same
// day replaces that day's front page instead of stacking a duplicate.
export function mergeArchive(archive = [], edition, limit = 7) {
  if (!edition) return Array.isArray(archive) ? archive.slice(0, limit) : [];
  const keep = (Array.isArray(archive) ? archive : []).filter(entry =>
    entry && entry.isoDate !== edition.isoDate && entry !== edition);
  return [edition, ...keep]
    .sort((a, b) => String(b.isoDate || '').localeCompare(String(a.isoDate || ''))
      || ((b.number || 0) - (a.number || 0)))
    .slice(0, Math.max(1, limit));
}

// What the UI persists per archived edition: the front page without the full text of every story.
export function editionSummary(edition) {
  return {
    number: edition.number,
    isoDate: edition.isoDate,
    dateLabel: edition.dateLabel,
    builtAt: edition.builtAt,
    leadTitle: edition.lead ? edition.lead.title : '',
    leadUrl: edition.lead ? edition.lead.url : '',
    headlines: edition.stories.slice(0, 6).map(story => ({ title: story.title, url: story.url, sources: story.sources })),
    printedStories: (edition.printedStories || []).slice(0, 40),
    // Keys only (link + headline): enough to recognise a repeat tomorrow, small enough to keep.
    printed: (edition.printed || []).slice(0, 80),
    storyCount: edition.storyCount,
    crossPosted: edition.crossPosted
  };
}

// What changed since the previous printing: the line a newspaper puts under the masthead.
export function editionDiff(current, previous) {
  if (!previous) {
    return { first: true, fresh: current.storyCount, carried: 0, dropped: 0,
      line: 'First edition. Everything here is new.' };
  }
  const returned = new Set(current.returned || []);
  const pairs = previous.printedStories
    || (previous.printed || []).reduce((out, key, index, all) =>
      (index % 2 ? out : out.concat([[key, all[index + 1] || '']])), []);
  const dropped = pairs.filter(([url, headline]) => !returned.has(url) && !returned.has(headline)).length;
  const fresh = current.storyCount;
  const carried = current.withheld;
  const parts = [`${fresh} new since No. ${previous.number}`];
  if (carried) parts.push(`${carried} still running`);
  if (dropped) parts.push(`${dropped} gone from your feeds`);
  return { first: false, fresh, carried, dropped, line: parts.join(' · ') };
}
