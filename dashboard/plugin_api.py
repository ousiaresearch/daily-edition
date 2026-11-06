import importlib.util
from pathlib import Path
from fastapi import APIRouter, Body
from pydantic import BaseModel


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feed = _load('daily_edition_feed', 'feed.py')
fetch_feed = feed.fetch_feed
fetch_topic = feed.fetch_topic
discover_sources = feed.discover_sources
parse_opml = feed.DISCOVERY.parse_opml
build_opml = feed.DISCOVERY.build_opml
router = APIRouter()

personas = _load('daily_edition_personas', 'personas.py')
model = _load('daily_edition_model', 'model_client.py')
reader = _load('daily_edition_reader', 'reader.py')
store = _load('daily_edition_state', 'state.py')
engine = _load('daily_edition_compose', 'compose.py')
press = _load('daily_edition_print', 'print.py')


class OpmlBody(BaseModel):
    text: str


class OpmlExport(BaseModel):
    feeds: list[str] = []
    interests: list[str] = []


class ComposeBody(BaseModel):
    persona: str
    stories: list[dict] = []
    limit: int = 12


class StateBody(BaseModel):
    interests: list[str] | None = None
    feeds: list[str] | None = None
    muted: list[str] | None = None
    watchwords: list[str] | None = None
    persona: str | None = None
    archive: list[dict] | None = None


class PrintBody(BaseModel):
    printer: str = ''
    dry_run: bool = False
    max_pages: int = 1
    max_stories: int = 20


@router.get('/feed')
def read_feed(url: str):
    try:
        return fetch_feed(url)
    except Exception as exc:
        return {'error': str(exc) or 'Could not load feed'}


@router.get('/article')
def read_article(url: str):
    """The publisher's page as plain text blocks for the in-app reader (never HTML)."""
    try:
        return reader.read_article(url)
    except Exception as exc:
        return {'error': str(exc) or 'Could not read that page', 'blocks': []}


@router.get('/discover')
def discover(url: str):
    """Turn any site URL into the feed(s) it offers, so a visitor can paste a homepage."""
    try:
        return discover_sources(url)
    except Exception as exc:
        return {'error': str(exc) or 'Could not read that URL', 'feeds': []}


@router.post('/opml')
def read_opml(body: OpmlBody = Body(...)):
    """Parse an exported subscription list (OPML) into addable sources."""
    try:
        return {'feeds': parse_opml(body.text)}
    except Exception as exc:
        return {'error': str(exc) or 'Not an OPML subscription list', 'feeds': []}


@router.post('/opml/export')
def export_opml(body: OpmlExport = Body(...)):
    """Hand the reader's sources back as OPML, so nothing is trapped in plugin storage."""
    entries = [{'title': '', 'url': url} for url in body.feeds]
    for phrase in body.interests:
        try:
            entries.append({'title': phrase, 'url': feed.TOPICS.topic_url(phrase)})
        except Exception:
            continue
    return {'text': build_opml(entries), 'count': len(entries)}


@router.get('/state')
def get_state():
    """The settings the agent side composes from (mirrored by the page)."""
    return store.read()


@router.post('/state')
def put_state(body: StateBody = Body(...)):
    try:
        return store.write(body.model_dump(exclude_none=True))
    except Exception as exc:
        return {'error': str(exc) or 'Could not save settings'}


@router.post('/print')
def print_paper(body: PrintBody = Body(...)):
    """Render the saved edition to a printable page and, unless dry_run, send it to a printer."""
    try:
        saved = store.read()
        edition, standfirst, errors = engine.compose(saved, max_stories=body.max_stories or 20)
        edition['standfirst'] = standfirst.get('line', '')
        result = press.print_edition(
            edition, printer=body.printer or '', dry_run=bool(body.dry_run),
            max_pages=max(1, min(int(body.max_pages or 1), 4)),
            source_urls=(saved.get('feeds') or []),
        )
        result['composeErrors'] = errors
        return result
    except Exception as exc:
        return {'ok': False, 'error': str(exc) or 'Could not print the edition'}


@router.get('/personas')
def list_personas():
    """The roster the page can offer, plus whether styling is possible at all."""
    config = model.settings()
    return {
        'personas': [{'id': key, 'name': value['name'], 'strapline': value['strapline']}
                     for key, value in personas.PERSONAS.items()],
        'configured': bool(config.get('configured')),
        'model': config.get('model', ''),
        'error': config.get('error', ''),
    }


@router.post('/compose')
def compose(body: ComposeBody = Body(...)):
    """Rewrite headlines in a persona's voice. On any failure the publisher's wording stands."""
    config = model.settings()
    if not config.get('configured'):
        return {'error': config.get('error') or 'Model not configured', 'items': []}
    stories = [{'title': str(s.get('title') or ''), 'snippet': str(s.get('snippet') or '')}
               for s in body.stories[:20] if isinstance(s, dict)]
    try:
        items = personas.compose_persona(body.persona, stories, lambda messages: model.chat(messages, config),
                                         limit=max(1, min(int(body.limit or 12), 20)))
    except ValueError as exc:
        return {'error': str(exc), 'items': []}
    return {'items': items, 'model': config['model'], 'persona': body.persona}


@router.get('/topic')
def read_topic(q: str):
    """An interest, expanded into its own section of the edition."""
    try:
        data = fetch_topic(q)
        data['interest'] = ' '.join(str(q).split())
        return data
    except Exception as exc:
        return {'error': str(exc) or 'Could not read that interest', 'items': [], 'interest': q}
