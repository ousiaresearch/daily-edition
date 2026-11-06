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

const CLUSTER_THRESHOLD = 0.6;

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

// Group items that are the same story: identical canonical link first, then headline overlap.
function cluster(sources) {
  const stories = [];
  for (const feed of sources) {
    for (const raw of (feed.items || [])) {
      const url = canonicalUrl(raw.url);
      const title = String(raw.title || '').trim();
      if (!url || !title) continue;
      const candidate = {
        title, url,
        snippet: String(raw.snippet || ''),
        date: String(raw.date || ''),
        at: timestamp(raw.date),
        sources: [feed.source],
        // Who filed it, as distinct from which interest surfaced it. Falls back to the feed name
        // so plain subscriptions keep working unchanged.
        publishers: [String(raw.publisher || feed.source)],
        also: [{ source: feed.source, url }]
      };
      const match = stories.find(story =>
        story.url === url || similarity(story.title, title) >= CLUSTER_THRESHOLD);
      if (!match) {
        stories.push(candidate);
        continue;
      }
      if (!match.sources.includes(feed.source)) match.sources.push(feed.source);
      const publisher = String(raw.publisher || feed.source);
      if (!match.publishers.includes(publisher)) match.publishers.push(publisher);
      if (!match.also.some(entry => entry.url === url)) match.also.push({ source: feed.source, url });
      // Keep the fullest available summary and the earliest date as the original filing.
      if (candidate.snippet.length > match.snippet.length) match.snippet = candidate.snippet;
      if (candidate.at && (!match.at || candidate.at < match.at)) {
        match.at = candidate.at;
        match.date = candidate.date;
      }
    }
  }
  return stories;
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
