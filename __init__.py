"""Daily Edition: the desktop page, its backend, and the agent's way into the paper.

The page composes its edition in the renderer. A tool, the `/edition` command and a cron job run in
the gateway, where the ported model in dashboard/edition.py composes the same paper from the
settings the page mirrors into dashboard/state.py. Nothing here calls a model.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
TOOLSET = 'daily-edition'
MAX_TEXT = 12_000


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / 'dashboard' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = {
    'name': 'daily_edition',
    'description': (
        "Print the reader's Daily Edition: a dated front page composed from their saved interests "
        "and feeds, with one story once (cross-posted stories merged), consensus winning the lead, "
        "and anything already printed in an earlier day withheld. Deterministic and model-free. "
        "Use it for morning briefings, cron jobs and questions about what is in today's paper. "
        "Actions: print (the front page as text), diff (what changed since the last edition), "
        "sources (what the paper is currently drawing on)."
    ),
    'parameters': {
        'type': 'object',
        'properties': {
            'action': {
                'type': 'string',
                'enum': ['print', 'diff', 'sources', 'print_paper'],
                'description': (
                    'What to return. Default: print (the front page as text). print_paper renders '
                    'the edition as a one-page PDF and sends it to a printer.'
                ),
            },
            'printer': {
                'type': 'string',
                'description': 'CUPS destination for print_paper. Omit to use the default printer.',
            },
            'dry_run': {
                'type': 'boolean',
                'description': 'With print_paper: render the page but do not print it.',
            },
            'interests': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    'Optional interest phrases to use instead of the saved ones for this call, '
                    'e.g. ["fusion energy", "housing in Málaga"]. Max 12.'
                ),
            },
            'max_stories': {
                'type': 'integer',
                'description': 'How many stories to print (1–40, default 20).',
                'minimum': 1,
                'maximum': 40,
            },
        },
        'required': [],
    },
}


def _state():
    return _load('daily_edition_state_entry', 'state.py')


def _compose():
    return _load('daily_edition_compose_entry', 'compose.py')


def _press():
    return _load('daily_edition_print_entry', 'print.py')


def _clean_interests(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError('interests must be a list of phrases')
    phrases = [' '.join(str(item).split()) for item in value if str(item).strip()]
    phrases = [phrase for phrase in phrases if len(phrase) <= 120]
    if len(phrases) > 12:
        raise ValueError('At most 12 interests per call')
    return phrases


def _print(max_stories, interests=None, record=True):
    store = _state()
    engine = _compose()
    current = store.read()
    result = engine.compose_and_render(current, max_stories=max_stories, interests=interests)
    edition = result['edition']
    if record and edition['storyCount']:
        summary = engine.edition_summary(edition)
        store.write({'archive': engine.merge_archive(current.get('archive') or [], summary, 7)})
    return result, current, engine


def _tool(args):
    args = args if isinstance(args, dict) else {}
    action = str(args.get('action') or 'print').lower()
    try:
        if action == 'sources':
            current = _state().read()
            interests = current.get('interests') or []
            feeds = current.get('feeds') or []
            muted = current.get('muted') or []
            lines = ['%d interest%s: %s' % (len(interests), '' if len(interests) == 1 else 's',
                                            ', '.join(interests) or 'none'),
                     '%d feed%s: %s' % (len(feeds), '' if len(feeds) == 1 else 's',
                                        ', '.join(feeds) or 'none'),
                     'muted: %s' % (', '.join(muted) or 'none'),
                     'voice: %s' % (current.get('persona') or 'house style')]
            return json.dumps({'action': 'sources', 'text': '\n'.join(lines),
                               'interests': interests, 'feeds': feeds, 'muted': muted},
                              ensure_ascii=False)

        interests = _clean_interests(args.get('interests'))
        max_stories = int(args.get('max_stories') or 20)
        max_stories = max(1, min(max_stories, 40))

        if action in ('print_paper', 'paper'):
            engine = _compose()
            press = _press()
            current = _state().read()
            edition, standfirst, errors = engine.compose(current, max_stories=max_stories,
                                                         interests=interests)
            edition['standfirst'] = standfirst.get('line', '')
            if edition['storyCount']:
                summary = engine.edition_summary(edition)
                _state().write({'archive': engine.merge_archive(current.get('archive') or [], summary, 7)})
            result = press.print_edition(
                edition, printer=str(args.get('printer') or ''),
                dry_run=bool(args.get('dry_run')), source_urls=current.get('feeds') or [],
            )
            result.update({'action': 'print_paper', 'errors': errors,
                           'standfirst': standfirst.get('line', '')})
            return json.dumps(result, ensure_ascii=False)

        if action == 'diff':
            engine = _compose()
            current = _state().read()
            edition, standfirst, errors = engine.compose(current, max_stories=max_stories,
                                                         interests=interests)
            return json.dumps({'action': 'diff', 'text': standfirst.get('line', ''),
                               'number': edition['number'], 'storyCount': edition['storyCount'],
                               'errors': errors}, ensure_ascii=False)

        result, current, engine = _print(max_stories, interests)
        edition = result['edition']
        payload = {
            'action': 'print',
            'text': result['text'][:MAX_TEXT],
            'number': edition['number'],
            'dateLabel': edition['dateLabel'],
            'storyCount': edition['storyCount'],
            'crossPosted': edition['crossPosted'],
            'withheld': edition['withheld'],
            'standfirst': result['standfirst'].get('line', ''),
            'errors': result['errors'],
            'voice': current.get('persona') or '',
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:  # a broken feed or state file is reported, never fatal
        return json.dumps({'error': str(exc) or 'Could not print the edition'}, ensure_ascii=False)


def _command(raw_args):
    argument = ' '.join(str(raw_args or '').split())
    lowered = argument.lower()
    if lowered in ('sources', 'sources?'):
        return json.loads(_tool({'action': 'sources'}))['text']
    if lowered in ('diff', 'what changed'):
        payload = json.loads(_tool({'action': 'diff'}))
        return payload.get('error') or '%s\nNo. %s · %s stories' % (
            payload['text'], payload['number'], payload['storyCount'])
    if lowered in ('paper', 'print', 'preview'):
        payload = json.loads(_tool({'action': 'print_paper', 'dry_run': lowered == 'preview'}))
        if payload.get('error'):
            return 'Daily Edition: %s' % payload['error']
        pages = payload.get('pages') or 0
        fact = '%s page%s, %s stories' % (pages, '' if pages == 1 else 's', payload.get('stories') or 0)
        if payload.get('dryRun'):
            return 'Rendered the paper to %s (%s). Nothing was sent to a printer.' % (
                payload.get('pdf') or payload.get('text'), fact)
        return 'Printed to %s — job %s (%s).' % (payload.get('printer'), payload.get('job'), fact)
    payload = json.loads(_tool({'action': 'print'}))
    if payload.get('error'):
        return 'Daily Edition: %s' % payload['error']
    return payload['text'] + ('\n\nSources that could not be read:\n- ' + '\n- '.join(payload['errors'])
                              if payload.get('errors') else '')


def register(ctx):
    """One tool and one command: the paper is readable from chat and from cron, not only the page."""
    ctx.register_tool(
        name=SCHEMA['name'], toolset=TOOLSET, schema=SCHEMA, handler=_tool,
        description='Print the reader’s dated Daily Edition from their saved interests and feeds',
        emoji='📰',
    )
    ctx.register_command(
        'edition', _command,
        description='Print today’s Daily Edition (or: /edition diff, /edition sources)',
        args_hint='[diff|sources]',
    )

