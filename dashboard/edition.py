"""The edition model, in Python, for the agent and cron side.

`desktop/edition.js` composes the paper for the page. A tool or a cron job has no renderer, so the
same model is ported here and kept honest by a parity test: `tests/test_edition_parity.py` builds
editions through both implementations from the same fixtures and fails if the outputs diverge.

Same rules as the JS: one story once (canonical link, then headline overlap), consensus wins the
lead, everything already printed in an earlier day is withheld, and an edition is dated by the
reader's local day.

Pure functions only — no network, no filesystem, no model.
"""

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit

TRACKING = re.compile(r'^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$|source$|igshid$)', re.I)

STOPWORDS = {
    'a', 'an', 'and', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'is', 'it', 'its', 'of', 'on',
    'or', 'that', 'the', 'to', 'was', 'were', 'will', 'with', 'after', 'before', 'over', 'under',
    'this', 'these', 'those', 'has', 'have', 'had', 'not', 'but', 'are', 'am', 'been', 'into',
}

CLUSTER_THRESHOLD = 0.6

_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
           'October', 'November', 'December')


def canonical_url(raw):
    """Same normalisation as the JS: drop the fragment, lowercase the host, drop tracking params."""
    text = str(raw or '').strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return ''
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return ''
    host = parts.hostname.lower()
    netloc = host
    default = 443 if parts.scheme == 'https' else 80
    if port and port != default:
        netloc = '%s:%s' % (host, port)
    params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
              if not TRACKING.match(key)]
    path = re.sub(r'/+$', '', parts.path) or '/'
    query = urlencode(params)
    return '%s://%s%s%s' % (parts.scheme, netloc, path, ('?' + query) if query else '')


def title_key(title):
    text = re.sub(r'[^\w\s]', ' ', str(title or '').lower(), flags=re.UNICODE).replace('_', ' ')
    return ' '.join(token for token in text.split() if token and token not in STOPWORDS)


def stem(word):
    if len(word) <= 4:
        return word
    word = re.sub(r'(ing|ed|es|s)$', '', word, count=1)
    return re.sub(r'([^aeiou])\1$', r'\1', word)


def tokens(title):
    return {stem(token) for token in title_key(title).split() if token}


def similarity(a, b):
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    shared = len(left & right)
    return shared / (len(left) + len(right) - shared)


def _timestamp(value):
    text = str(value or '').strip()
    if not text:
        return 0
    moment = None
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        moment = None
    if moment is None:
        probe = text[:-1] + '+00:00' if text.endswith('Z') else text
        for candidate in (probe, text):
            try:
                moment = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
    if moment is None:
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return int(moment.timestamp() * 1000)


def local_iso(date):
    return '%04d-%02d-%02d' % (date.year, date.month, date.day)


def date_label(date):
    return '%s, %d %s %d' % (_WEEKDAYS[date.weekday()], date.day, _MONTHS[date.month - 1], date.year)


ACTION_FAMILY = {
    'approve': 'decide', 'approves': 'decide', 'approved': 'decide',
    'pass': 'decide', 'passes': 'decide', 'passed': 'decide',
    'adopt': 'decide', 'adopts': 'decide', 'adopted': 'decide',
    'vote': 'decide', 'votes': 'decide', 'voted': 'decide',
    'clear': 'decide', 'clears': 'decide', 'cleared': 'decide',
    'back': 'decide', 'backs': 'decide', 'backed': 'decide',
    'decide': 'decide', 'decides': 'decide', 'decided': 'decide',
    'reject': 'refuse', 'rejects': 'refuse', 'rejected': 'refuse',
    'block': 'refuse', 'blocks': 'refuse', 'blocked': 'refuse',
    'veto': 'refuse', 'vetoes': 'refuse', 'vetoed': 'refuse',
    'deny': 'refuse', 'denies': 'refuse', 'denied': 'refuse',
    'delay': 'delay', 'delays': 'delay', 'delayed': 'delay',
    'postpone': 'delay', 'postponed': 'delay', 'shelve': 'delay', 'shelved': 'delay',
    'suspend': 'delay', 'suspended': 'delay',
    'rise': 'up', 'rises': 'up', 'rising': 'up', 'climb': 'up', 'climbs': 'up', 'climbed': 'up',
    'increase': 'up', 'increases': 'up', 'soar': 'up', 'soars': 'up', 'gain': 'up', 'gains': 'up',
    'fall': 'down', 'falls': 'down', 'fell': 'down', 'drop': 'down', 'drops': 'down', 'dropped': 'down',
    'decline': 'down', 'declines': 'down', 'cut': 'down', 'cuts': 'down', 'plunge': 'down', 'plunges': 'down',
    'launch': 'begin', 'launches': 'begin', 'launched': 'begin', 'unveil': 'begin', 'unveils': 'begin',
    'open': 'begin', 'opens': 'begin', 'opened': 'begin', 'release': 'begin', 'releases': 'begin',
    'start': 'begin', 'starts': 'begin',
    'close': 'end', 'closes': 'end', 'closed': 'end', 'shut': 'end', 'shuts': 'end',
    'halt': 'end', 'halts': 'end',
    'warn': 'warn', 'warns': 'warn', 'warned': 'warn', 'warning': 'warn', 'alert': 'warn', 'alerts': 'warn',
}

_YEARS = re.compile(r'\b(?:19|20)\d{2}\b')


def _action_families(title):
    return {ACTION_FAMILY[word] for word in title_key(title).split(' ') if word in ACTION_FAMILY}


def _years(title):
    return set(_YEARS.findall(str(title or '')))


def _conflicting_years(a, b):
    left, right = _years(a), _years(b)
    if not left or not right:
        return False
    return not (left & right)


def _compatible_actions(a, b):
    left, right = _action_families(a), _action_families(b)
    if not left or not right:
        return True
    return bool(left & right)


def _content_bigrams(title):
    words = [word for word in title_key(title).split(' ') if len(word) >= 4]
    return {words[i] + ' ' + words[i + 1] for i in range(len(words) - 1)}


def _shares_bigram(a, b):
    return bool(_content_bigrams(a) & _content_bigrams(b))


def same_story(a, b):
    """One story, once — the Python twin of sameStory() in desktop/edition.js."""
    if a.get('url') and a.get('url') == b.get('url'):
        return True
    if _conflicting_years(a.get('title'), b.get('title')):
        return False
    if not _compatible_actions(a.get('title'), b.get('title')):
        return False
    left, right = tokens(a.get('title')), tokens(b.get('title'))
    shared = len(left & right)
    min_size = min(len(left), len(right))
    if not shared or not min_size:
        return False
    containment = shared / min_size
    jaccard = shared / (len(left) + len(right) - shared)
    score = 0.65 * containment + 0.35 * jaccard
    if score >= 0.66 and shared >= 3:
        return True
    publishers_a = a.get('publishers') or []
    publishers_b = b.get('publishers') or []
    if any(name in publishers_b for name in publishers_a):
        return False
    if shared >= 2 and _shares_bigram(a.get('title'), b.get('title')):
        return True
    return containment >= 0.9 and min_size >= 3


def _cluster(sources):
    items = []
    for feed in sources:
        for raw in (feed.get('items') or []):
            url = canonical_url(raw.get('url'))
            title = str(raw.get('title') or '').strip()
            if not url or not title:
                continue
            items.append({
                'title': title,
                'url': url,
                'snippet': str(raw.get('snippet') or ''),
                'date': str(raw.get('date') or ''),
                'at': _timestamp(raw.get('date')),
                'sources': [feed.get('source')],
                'publishers': [str(raw.get('publisher') or feed.get('source'))],
                'also': [{'source': feed.get('source'), 'url': url}],
            })

    parent = list(range(len(items)))

    def find(index):
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:
            parent[index], index = root, parent[index]
        return root

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if same_story(items[i], items[j]):
                root_i, root_j = find(i), find(j)
                if root_i != root_j:
                    parent[max(root_i, root_j)] = min(root_i, root_j)

    groups = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)

    stories = []
    for group in groups.values():
        story = dict(group[0])
        story['sources'] = list(group[0]['sources'])
        story['publishers'] = list(group[0]['publishers'])
        story['also'] = list(group[0]['also'])
        for item in group[1:]:
            for source in item['sources']:
                if source not in story['sources']:
                    story['sources'].append(source)
            for publisher in item['publishers']:
                if publisher not in story['publishers']:
                    story['publishers'].append(publisher)
            known_urls = {known['url'] for known in story['also']}
            for entry in item['also']:
                if entry['url'] not in known_urls:
                    story['also'].append(entry)
                    known_urls.add(entry['url'])
            if len(item['snippet']) > len(story['snippet']):
                story['snippet'] = item['snippet']
            if item['at'] and (not story['at'] or item['at'] < story['at']):
                story['at'] = item['at']
                story['date'] = item['date']
        stories.append(story)
    return stories


def _rank(stories):
    def key(pair):
        index, story = pair
        return (
            -int(bool(story.get('pinned'))),
            -len(story.get('publishers') or []),
            -story.get('at', 0),
            index,
        )
    return [story for _, story in sorted(enumerate(stories), key=key)]


def matches_watchword(story, watchwords):
    words = [stem(str(word).lower()) for word in (watchwords or []) if str(word).strip()]
    if not words:
        return False
    haystack = tokens(story.get('title')) | tokens(story.get('snippet') or '')
    return any(word in haystack for word in words)


def build_edition(sources=None, previous=None, now=None, max_stories=20, muted=None, watchwords=None):
    built = now if isinstance(now, datetime) else datetime.fromisoformat(str(now))
    if built.tzinfo is None:
        built = built.astimezone()
    sources = sources or []
    muted_set = {str(name).lower() for name in (muted or [])}
    active = [feed for feed in sources if str(feed.get('source') or '').lower() not in muted_set]
    muted_count = sum(1 for feed in sources if str(feed.get('source') or '').lower() in muted_set)

    withheld_keys = set((previous or {}).get('printed') or [])
    everything = [dict(story, pinned=matches_watchword(story, watchwords)) for story in _cluster(active)]

    fresh, withheld_stories, withheld = [], [], 0
    for story in everything:
        if story['url'] in withheld_keys or title_key(story['title']) in withheld_keys:
            withheld += 1
            withheld_stories.append(story)
            continue
        fresh.append(story)

    ordered = _rank(fresh)
    printed = ordered[:max_stories]
    omitted = len(ordered) - len(printed)
    lead = printed[0] if printed else None

    sections = []
    for story in printed[1:]:
        source = (story.get('sources') or [''])[0]
        section = next((entry for entry in sections if entry['source'] == source), None)
        if section is None:
            section = {'source': source, 'stories': []}
            sections.append(section)
        section['stories'].append(story)

    keys = lambda stories: [key for story in stories for key in (story['url'], title_key(story['title'])) if key]
    return {
        'number': int((previous or {}).get('number') or 0) + 1,
        'isoDate': local_iso(built),
        'dateLabel': date_label(built),
        'builtAt': built.isoformat(),
        'lead': lead,
        'sections': sections,
        'stories': printed,
        'printed': keys(printed)[:160],
        'printedStories': [[story['url'], title_key(story['title'])] for story in printed],
        'returned': keys(printed + withheld_stories),
        'withheld': withheld,
        'omitted': omitted,
        'crossPosted': sum(1 for story in printed if len(story.get('publishers') or []) > 1),
        'mutedCount': muted_count,
        'pinnedCount': sum(1 for story in printed if story.get('pinned')),
        'sourceCount': sum(1 for feed in sources if feed.get('items')),
        'storyCount': len(printed),
    }


def merge_archive(archive=None, edition=None, limit=7):
    archive = archive if isinstance(archive, list) else []
    if not edition:
        return archive[:limit]
    keep = [entry for entry in archive if entry and entry.get('isoDate') != edition.get('isoDate')]
    merged = [edition] + keep
    merged.sort(key=lambda entry: (str(entry.get('isoDate') or ''), entry.get('number') or 0), reverse=True)
    return merged[:max(1, limit)]


def edition_summary(edition):
    return {
        'number': edition['number'],
        'isoDate': edition['isoDate'],
        'dateLabel': edition['dateLabel'],
        'builtAt': edition['builtAt'],
        'leadTitle': (edition.get('lead') or {}).get('title', ''),
        'leadUrl': (edition.get('lead') or {}).get('url', ''),
        'headlines': [{'title': story['title'], 'url': story['url'], 'sources': story.get('sources')}
                      for story in edition['stories'][:6]],
        'printedStories': (edition.get('printedStories') or [])[:40],
        'printed': (edition.get('printed') or [])[:80],
        'storyCount': edition['storyCount'],
        'crossPosted': edition['crossPosted'],
    }


def edition_diff(current, previous):
    if not previous:
        return {'first': True, 'fresh': current['storyCount'], 'carried': 0, 'dropped': 0,
                'line': 'First edition. Everything here is new.'}
    returned = set(current.get('returned') or [])
    pairs = previous.get('printedStories')
    if not pairs:
        flat = previous.get('printed') or []
        pairs = [[flat[index], flat[index + 1] if index + 1 < len(flat) else '']
                 for index in range(0, len(flat), 2)]
    dropped = sum(1 for pair in pairs if pair[0] not in returned and pair[1] not in returned)
    fresh = current['storyCount']
    carried = current.get('withheld') or 0
    parts = ['%d new since No. %s' % (fresh, previous.get('number'))]
    if carried:
        parts.append('%d still running' % carried)
    if dropped:
        parts.append('%d gone from your feeds' % dropped)
    return {'first': False, 'fresh': fresh, 'carried': carried, 'dropped': dropped,
            'line': ' · '.join(parts)}
