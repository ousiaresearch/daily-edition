"""Where the paper's settings live for the parts of Hermes that are not the page.

`desktop/plugin.js` keeps the reader's settings in its own namespaced storage, which only the
renderer can read. A tool, a slash command and a cron job run in the gateway, so the page mirrors
its settings here through `POST /state`, and the agent side reads them back. One file per profile:

    $HERMES_HOME/plugin-data/daily-edition/state.json

Contents are interests, feed URLs, mutes, watchwords, the chosen voice and the summaries of past
editions (headlines and links only — never article bodies). The file is written 0600 and replaced
atomically, so a concurrent read never sees a half-written paper.
"""

import json
import os
import pathlib
import tempfile

MAX_INTERESTS = 30
MAX_FEEDS = 60
MAX_ARCHIVE = 7

DEFAULTS = {
    'interests': [],
    'feeds': [],
    'muted': [],
    'watchwords': [],
    'persona': '',
    'archive': [],
    'updated': '',
}


def home():
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        return pathlib.Path(os.environ.get('HERMES_HOME') or (pathlib.Path.home() / '.hermes'))
    return pathlib.Path(get_hermes_home())


def state_path():
    return home() / 'plugin-data' / 'daily-edition' / 'state.json'


def _clean_list(value, limit):
    out = []
    for item in value or []:
        text = ' '.join(str(item).split()) if isinstance(item, str) else ''
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalise(patch):
    """Keep only the keys we own, and keep each of them small and boring."""
    data = {}
    if isinstance(patch.get('interests'), list):
        data['interests'] = _clean_list(patch['interests'], MAX_INTERESTS)
    if isinstance(patch.get('feeds'), list):
        data['feeds'] = _clean_list(patch['feeds'], MAX_FEEDS)
    if isinstance(patch.get('muted'), list):
        data['muted'] = _clean_list(patch['muted'], 100)
    if isinstance(patch.get('watchwords'), list):
        data['watchwords'] = _clean_list([w.lower() for w in patch['watchwords'] if isinstance(w, str)], 24)
    if isinstance(patch.get('persona'), str):
        data['persona'] = patch['persona'][:60]
    if isinstance(patch.get('archive'), list):
        kept = []
        for entry in patch['archive'][:MAX_ARCHIVE]:
            if not isinstance(entry, dict):
                continue
            kept.append({key: entry.get(key) for key in
                         ('number', 'isoDate', 'dateLabel', 'leadTitle', 'leadUrl', 'storyCount',
                          'crossPosted', 'printed', 'printedStories', 'headlines')
                         if key in entry})
        data['archive'] = kept
    return data


def read():
    """The saved settings, or the defaults when nothing has been saved yet."""
    path = state_path()
    if not path.exists():
        path = home() / 'daily-edition' / 'state.json'
    try:
        stored = json.loads(path.read_text('utf-8'))
        if not isinstance(stored, dict):
            raise ValueError('state is not an object')
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (OSError, ValueError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(normalise(stored))
    return merged


def write(patch):
    """Merge a patch into the state file atomically; returns the merged state."""
    current = read()
    current.update(normalise(patch or {}))
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.state-', suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(current, stream, ensure_ascii=False, indent=1)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return current
