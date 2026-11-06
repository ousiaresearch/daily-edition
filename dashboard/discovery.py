"""Source discovery: find feeds a site advertises, and read an OPML subscription list.

Pure parsing only — no network. The caller decides what to fetch, so the safety rules that
apply to fetching (public hosts, ports 80/443, no redirects) stay in one place in feed.py.
"""

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

FEED_TYPES = {
    'application/rss+xml',
    'application/atom+xml',
    'application/x-atom+xml',
    'application/feed+json',
    'application/json',
    'text/xml',
    'application/xml',
}

MAX_HTML_BYTES = 512_000


def _safe_http(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        return False
    if parts.username or parts.password:
        return False
    return parts.port in (None, 80, 443)


class _Alternates(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'link':
            return
        values = {name.lower(): (value or '') for name, value in attrs}
        rels = values.get('rel', '').lower().split()
        mime = values.get('type', '').split(';')[0].strip().lower()
        href = values.get('href', '').strip()
        if 'alternate' in rels and mime in FEED_TYPES and href:
            self.found.append((href, values.get('title', '').strip()))


def extract_feed_links(html, base_url):
    """Feed URLs a page advertises via <link rel="alternate">, absolute and de-duplicated."""
    text = html.decode('utf-8', 'replace') if isinstance(html, (bytes, bytearray)) else str(html or '')
    parser = _Alternates()
    try:
        parser.feed(text[:MAX_HTML_BYTES])
    except Exception:
        return []
    out, seen = [], set()
    for href, title in parser.found:
        absolute = urljoin(base_url, href)
        if not _safe_http(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        out.append({'url': absolute, 'title': title})
    return out


def looks_like_feed(data):
    """True when a response body is itself a feed, so a pasted feed URL is not mistaken for a page."""
    head = (data or b'')[:4096]
    if isinstance(head, str):
        head = head.encode('utf-8', 'replace')
    stripped = head.lstrip(b'\xef\xbb\xbf').lstrip()
    if stripped.startswith(b'<'):
        body = stripped.lower()
        if body.startswith(b'<rss') or body.startswith(b'<feed') or body.startswith(b'<rdf'):
            return True
        # A declaration or comment can precede the root element.
        return bool(re.search(rb'<(rss|feed|rdf:rdf)[\s>]', body[:2048]))
    return b'"version"' in stripped and b'jsonfeed' in stripped.lower()


def _local(tag):
    return tag.rsplit('}', 1)[-1].lower()


def parse_opml(text):
    """Return [{title, url}] from an OPML subscription list, rejecting anything unsafe."""
    if not isinstance(text, str):
        text = (text or b'').decode('utf-8', 'replace')
    if not text.strip():
        raise ValueError('Empty document')
    upper = text.upper()
    if '<!DOCTYPE' in upper or '<!ENTITY' in upper:
        raise ValueError('Unsupported XML declaration')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError('Not valid XML') from exc
    if _local(root.tag) != 'opml':
        raise ValueError('Not an OPML document')

    feeds, seen = [], set()

    def walk(node):
        for child in list(node):
            if _local(child.tag) != 'outline':
                continue
            xml_url = (child.get('xmlUrl') or child.get('xmlurl') or '').strip()
            if xml_url and _safe_http(xml_url) and xml_url not in seen:
                seen.add(xml_url)
                title = (child.get('title') or child.get('text') or '').strip()
                feeds.append({'title': title, 'url': xml_url})
            walk(child)

    body = next((child for child in root if _local(child.tag) == 'body'), root)
    walk(body)
    return feeds


def build_opml(entries):
    """Render subscriptions as an OPML 2.0 document, so a reader can leave with its sources."""
    import html
    import ipaddress

    def escape(value):
        return html.escape(str(value or ''), quote=True)

    def exportable(url):
        # Never hand out a URL that points at the reader's own machine or network.
        if not _safe_http(url):
            return False
        host = urlsplit(url).hostname or ''
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True

    outlines = []
    for entry in entries or []:
        url = str((entry or {}).get('url') or '').strip()
        if not exportable(url):
            continue
        title = str(entry.get('title') or url)
        outlines.append(
            '    <outline type="rss" text="%s" title="%s" xmlUrl="%s" />'
            % (escape(title), escape(title), escape(url))
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<opml version="2.0">\n'
            '  <head>\n'
            '    <title>Daily Edition subscriptions</title>\n'
            '  </head>\n'
            '  <body>\n'
            + ('\n'.join(outlines) + '\n' if outlines else '')
            + '  </body>\n'
            '</opml>\n')
