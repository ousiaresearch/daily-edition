"""In-app reading: turn a publisher's article page into plain, safe text blocks.

The page is untrusted, so nothing from it is ever handed back as HTML. The extractor emits an
ordered list of typed text blocks (heading, paragraph, list item, quotation) and the desktop
renders each one as a text node. There is therefore no sanitizer to get wrong: no tags, no
attributes, no inline styles, no images, no scripts reach the renderer.

This is a readability-style heuristic, not a full article extractor: it drops the chrome
(navigation, footers, sidebars, forms, scripts), keeps the longest run of prose-bearing blocks
and reports how much text it got so the UI can offer the original when extraction is thin.
"""

import importlib.util
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_BLOCKS = 400
MAX_CHARS = 60_000
MIN_PARAGRAPH_CHARS = 25

# Tags whose entire subtree is not article text.
SKIP_TAGS = {
    'script', 'style', 'nav', 'aside', 'footer', 'form', 'noscript', 'svg', 'iframe',
    'template', 'button', 'select', 'option', 'textarea', 'canvas', 'video', 'audio',
}

# Block-level tags that start a new text block when they contain text.
BLOCK_TAGS = {
    'p': 'p', 'li': 'li', 'blockquote': 'quote', 'pre': 'p', 'dd': 'p',
    'h1': 'h2', 'h2': 'h2', 'h3': 'h2', 'h4': 'h3',
}

VOID_BREAKS = {'br', 'hr'}

# Short blocks that are almost always site chrome rather than prose.
CHROME = re.compile(
    r'(cookie|accept all|subscribe|sign in|log in|newsletter|advertisement|share this|'
    r'read more|related articles|all rights reserved|privacy policy|terms of service)',
    re.I,
)


def _load_feed():
    spec = importlib.util.spec_from_file_location(
        'daily_edition_feed_reader', pathlib.Path(__file__).with_name('feed.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.skip_depth = 0
        self.open_block = None
        self.buffer = []
        self.title = ''
        self.site = ''
        self._in_title = False
        self._h1 = ''

    # -- collection ---------------------------------------------------------------------
    def _flush(self):
        text = ' '.join(''.join(self.buffer).split())
        kind, self.open_block, self.buffer = self.open_block, None, []
        if not text:
            return
        if len(text) < MIN_PARAGRAPH_CHARS and (kind in (None, 'p') and not CHROME.search(text)):
            # Very short paragraphs are usually labels; keep one-word quotations out too.
            if kind != 'quote':
                return
        if len(text) < 3:
            return
        self.blocks.append({'type': kind or 'p', 'text': text})

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = True
            return
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in VOID_BREAKS:
            if self.buffer:
                self.buffer.append(' ')
            return
        if tag in BLOCK_TAGS:
            if self.buffer:
                self._flush()
            self.open_block = BLOCK_TAGS[tag]
            return
        if tag == 'img':
            alt = dict(attrs).get('alt') or ''
            # Alt text is the only thing worth keeping from an image; never the pixels.
            if alt and self.buffer:
                self.buffer.append(' ' + alt + ' ')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = False
            return
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS and self.open_block:
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self.skip_depth:
            return
        self.buffer.append(data)


class _Meta(HTMLParser):
    """Reads the hints a page gives about itself: description, author, site name, canonical."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.canonical = ''
        self.h1 = []
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        values = {name.lower(): (value or '') for name, value in attrs}
        if tag.lower() == 'meta':
            key = (values.get('property') or values.get('name') or '').lower()
            content = values.get('content') or ''
            if key in ('og:title', 'twitter:title') and content:
                self.meta.setdefault('title', content)
            elif key in ('og:site_name', 'application-name') and content:
                self.meta.setdefault('site', content)
            elif key in ('description', 'og:description') and content:
                self.meta.setdefault('description', content)
            elif key in ('author', 'article:author') and content:
                self.meta.setdefault('author', content)
        elif tag.lower() == 'link' and 'canonical' in (values.get('rel') or '').lower():
            self.canonical = values.get('href') or ''
        elif tag.lower() == 'h1':
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag.lower() == 'h1':
            self._in_h1 = False

    def handle_data(self, data):
        if self._in_h1:
            self.h1.append(data)


def _text(value, limit=400):
    return ' '.join(str(value or '').split())[:limit]


def extract(html, base_url=''):
    """Extract a readable article from an HTML document.

    Returns ``{title, site, description, blocks, words, truncated}`` where every block is
    ``{type: 'h2'|'h3'|'p'|'li'|'quote', text: str}``. Raises ValueError when the document has
    no usable prose, so the UI can offer the publisher's page instead of an empty pane.
    """
    if isinstance(html, bytes):
        raw = html.decode('utf-8', 'replace')
    else:
        raw = str(html or '')
    if not raw.strip():
        raise ValueError('That page was empty')

    body = _Blocks()
    try:
        body.feed(raw)
        body.close()
    except Exception as exc:  # malformed markup is not a reason to lose the page
        if not body.blocks:
            raise ValueError('That page could not be read') from exc
    body._flush()

    meta = _Meta()
    try:
        meta.feed(raw)
    except Exception:
        pass

    blocks, seen, chars = [], set(), 0
    truncated = False
    for block in body.blocks:
        text = block['text']
        key = text.lower()
        if key in seen:
            continue
        if block['type'] not in ('h2', 'h3') and CHROME.search(text) and len(text) < 90:
            continue
        seen.add(key)
        if chars + len(text) > MAX_CHARS or len(blocks) >= MAX_BLOCKS:
            truncated = True
            break
        blocks.append(block)
        chars += len(text)

    prose = [block for block in blocks if block['type'] in ('p', 'quote', 'li')]
    if not prose:
        raise ValueError('No article text found on that page')

    title = (_text(meta.meta.get('title')) or _text(' '.join(meta.h1))
             or _text(body.title) or _text((prose[0] or {}).get('text', ''), 120))
    site = ''
    if meta.canonical:
        site = urljoin(base_url or meta.canonical, meta.canonical)
    return {
        'title': title,
        'site': _text(meta.meta.get('site'), 80) or (urlsplit(base_url).hostname or ''),
        'description': _text(meta.meta.get('description'), 500),
        'author': _text(meta.meta.get('author'), 120),
        'canonical': site,
        'blocks': blocks,
        'words': len(' '.join(block['text'] for block in prose).split()),
        'truncated': truncated,
    }


def read_article(url, fetch=None):
    """Fetch a public article URL and extract it. ``fetch`` is injectable for tests."""
    feed = _load_feed()
    fetch = fetch or feed.fetch_document
    final, content_type, body = fetch(url)
    if content_type and 'html' not in content_type and 'xml' not in content_type:
        raise ValueError('That link is not a web page (%s)' % content_type)
    article = extract(body, final)
    article['url'] = final
    return article
