"""Compose the edition for the agent side of the house.

The page composes in the renderer; a tool, `/edition` and a cron job run in the gateway and have no
renderer. This module gathers the same sources (interests and plain feeds), builds the edition with
the ported model in `edition.py`, and renders a plain-text front page plus the standfirst.

Fetching is bounded: at most FETCH_WORKERS requests in flight, each with the same 12 s timeout and
2 MB cap as the page, and every failure is reported rather than hidden. Nothing here calls a model.
"""

import importlib.util
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

FETCH_WORKERS = 6


def _load(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, pathlib.Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_edition = _load('edition.py', 'daily_edition_model')
_feed = _load('feed.py', 'daily_edition_feed_compose')

build_edition = _edition.build_edition
edition_diff = _edition.edition_diff
edition_summary = _edition.edition_summary
merge_archive = _edition.merge_archive


def gather(interests, feeds):
    """Fetch every source in parallel. Returns (sources, errors); a bad source never sinks the paper."""
    tasks = [('interest:%s' % name, name, ('topic', name)) for name in interests or []]
    tasks += [(url, '', ('feed', url)) for url in feeds or []]
    sources, errors = [], []

    def one(task):
        key, label, (kind, value) = task
        try:
            data = _feed.fetch_topic(value) if kind == 'topic' else _feed.fetch_feed(value)
            return {'url': key, 'source': label or data.get('source') or key,
                    'items': data.get('items') or []}, None
        except Exception as exc:  # reported, never swallowed
            return None, '%s: %s' % (label or key, exc)

    if not tasks:
        return sources, errors
    with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(tasks))) as pool:
        futures = [pool.submit(one, task) for task in tasks]
        for future in as_completed(futures):
            source, error = future.result()
            if source:
                sources.append(source)
            if error:
                errors.append(error)
    return sources, errors


def compose(state, now=None, max_stories=20, interests=None, feeds=None):
    """Build an edition from the saved state (or an explicit interest list)."""
    chosen = interests if interests is not None else state.get('interests') or []
    chosen_feeds = feeds if feeds is not None else state.get('feeds') or []
    sources, errors = gather(chosen, chosen_feeds)
    archive = state.get('archive') or []
    moment = now or datetime.now().astimezone()
    iso = moment.strftime('%Y-%m-%d')
    previous = next((entry for entry in archive if entry.get('isoDate') != iso), None)
    edition = build_edition(
        sources=sources, previous=previous, now=moment,
        max_stories=max(1, min(int(max_stories or 20), 40)),
        muted=state.get('muted') or [], watchwords=state.get('watchwords') or [],
    )
    return edition, edition_diff(edition, previous), errors


def render(edition, standfirst, errors, interest_count=0):
    """A plain-text front page: masthead, standfirst, lead, sections, then what failed."""
    if not edition['storyCount']:
        head = 'DAILY EDITION — No. %s — %s' % (edition['number'], edition['dateLabel'])
        lines = [head, '', standfirst.get('line', '')]
        if edition.get('withheld'):
            lines.append('%d stor%s already ran in an earlier edition and was withheld.'
                         % (edition['withheld'], 'y' if edition['withheld'] == 1 else 'ies'))
        if errors:
            lines += ['', 'Sources that could not be read:'] + ['- ' + error for error in errors]
        return '\n'.join(line for line in lines if line is not None)

    lines = [
        'DAILY EDITION — No. %s — %s' % (edition['number'], edition['dateLabel']),
        standfirst.get('line', ''),
        '%d stories from %d %s · %d cross-posted · %d withheld · %d held over'
        % (edition['storyCount'], edition['sourceCount'],
           'source' if edition['sourceCount'] == 1 else 'sources',
           edition['crossPosted'], edition['withheld'], edition['omitted']),
        '',
    ]
    lead = edition['lead']
    lines += [
        'LEAD: ' + lead['title'],
        '  ' + ' · '.join(lead.get('publishers') or lead.get('sources') or []) + ' — ' + lead['url'],
    ]
    if lead.get('snippet'):
        lines.append('  ' + lead['snippet'][:300])
    for section in edition['sections']:
        lines += ['', section['source'].upper()]
        for story in section['stories']:
            byline = ' · '.join(story.get('publishers') or story.get('sources') or [])
            lines.append('  %s%s — %s' % ('★ ' if story.get('pinned') else '', story['title'], byline))
            lines.append('    ' + story['url'])
    if errors:
        lines += ['', 'Sources that could not be read:'] + ['- ' + error for error in errors]
    return '\n'.join(lines)


def compose_and_render(state, max_stories=20, interests=None, now=None):
    """One call for the tool and the command: compose, render, and record the edition."""
    edition, standfirst, errors = compose(state, now=now, max_stories=max_stories, interests=interests)
    text = render(edition, standfirst, errors)
    return {'text': text, 'edition': edition, 'standfirst': standfirst, 'errors': errors}
