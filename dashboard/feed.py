import importlib.util
import pathlib
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_DISCOVERY_BYTES = 512_000


def _load_discovery():
    """Sibling module by path: this file is loaded via importlib by the plugin host, so the
    dashboard directory is not necessarily on sys.path."""
    spec = importlib.util.spec_from_file_location(
        "daily_edition_discovery", pathlib.Path(__file__).with_name("discovery.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISCOVERY = _load_discovery()


def _load_sibling(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, pathlib.Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOPICS = _load_sibling("daily_edition_topics", "topics.py")

class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)

def plain(value):
    parser = Text()
    parser.feed(value or '')
    return ' '.join(' '.join(parser.parts).split())[:500]

def parse_feed(data, base):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or b'\x00' in data:
        raise ValueError('Unsupported XML declaration or encoding')
    root = ET.fromstring(data)
    atom = '{http://www.w3.org/2005/Atom}'
    if root.tag == atom + 'feed':
        source = root.findtext(atom + 'title', default='')
        nodes = root.findall(atom + 'entry')
        prefix = atom
    elif root.tag == 'rss' and root.find('channel') is not None:
        channel = root.find('channel')
        source = channel.findtext('title', default='')
        nodes = channel.findall('item')
        prefix = ''
    else:
        raise ValueError('Not an RSS or Atom feed')
    items = []
    for node in nodes[:100]:
        link = node.find(prefix + 'link')
        href = (link.get('href', '') if prefix else (link.text or '')) if link is not None else ''
        url = urljoin(base, href)
        parts = urlsplit(url)
        if not href or parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            continue
        title = plain(node.findtext(prefix + 'title', default=''))
        if not title:
            continue
        snippet = node.findtext(prefix + ('summary' if prefix else 'description'), default='')
        items.append({'title': title, 'url': url, 'snippet': plain(snippet), 'date': plain(node.findtext(prefix + ('published' if prefix else 'pubDate'), default=''))})
    return {'source': plain(source) or urlsplit(base).hostname, 'items': items}

def checked_target(url):
    import ipaddress, socket
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("Use a public HTTP(S) URL without credentials or fragment")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Only ports 80 and 443 are allowed")
    addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global or ipaddress.ip_address(a[4][0]).is_multicast for a in addresses):
        raise ValueError("Feed address is not public")
    return addresses[0][4][0], port

MAX_REDIRECTS = 3


def request_page(url, limit=512_000, timeout=12, truncate=False):
    """GET a public URL with the same safety rules as feed fetching; returns (final_url, headers, body).

    Redirects are followed up to MAX_REDIRECTS hops, and every hop is re-vetted by checked_target:
    a publisher may redirect a public feed to a loopback or metadata address, and following it
    blindly would turn a feed reader into an SSRF proxy.
    """
    return _request(url, limit=limit, timeout=timeout, truncate=truncate, hops=MAX_REDIRECTS)


def _request(url, limit, timeout, truncate, hops):
    import http.client, socket
    ip, port = checked_target(url)
    parts = urlsplit(url)
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = cls(parts.hostname, port, timeout=timeout)
    conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection((ip, port), timeout, source_address)
    try:
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        conn.request("GET", path, headers={
            "User-Agent": "Daily-Edition/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/feed+json, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
        })
        response = conn.getresponse()
        headers = dict(response.getheaders())
        if 300 <= response.status < 400:
            location = next((value for key, value in response.getheaders() if key.lower() == "location"), "")
            if not location:
                raise ValueError("Server returned HTTP %s without a Location header" % response.status)
            if hops <= 0:
                raise ValueError("Too many redirects (limit %s)" % MAX_REDIRECTS)
            return _request(urljoin(url, location), limit=limit, timeout=timeout,
                            truncate=truncate, hops=hops - 1)
        if response.status != 200:
            raise ValueError("Server returned HTTP %s" % response.status)
        data = response.read(limit + 1)
        if len(data) > limit:
            if not truncate:
                raise ValueError("Response exceeded %s bytes" % limit)
            # Discovery only needs <head>: a large homepage is not a reason to refuse, but a feed
            # truncated mid-document would parse as corrupt, so strict callers still get an error.
            data = data[:limit]
        return url, headers, data
    finally:
        conn.close()


def fetch_document(url, limit=2_000_000, timeout=12):
    """Fetch an article page for the in-app reader; returns (final_url, content_type, body)."""
    final, headers, data = request_page(url, limit=limit, timeout=timeout)
    content_type = (headers.get("Content-Type") or headers.get("content-type") or "").split(";")[0].strip().lower()
    return final, content_type, data


def fetch_feed(url):
    final, _, data = request_page(url, limit=2_000_000)
    return parse_feed(data, final)


COMMON_FEED_PATHS = ("/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml")


def discover_sources(url):
    """Given any public URL, return the feeds it advertises (or offer itself when it is one)."""
    extract_feed_links, looks_like_feed = DISCOVERY.extract_feed_links, DISCOVERY.looks_like_feed
    final, headers, body = request_page(url, limit=MAX_DISCOVERY_BYTES, timeout=10, truncate=True)
    content_type = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
    if looks_like_feed(body):
        return {"feeds": [{"url": final, "title": ""}], "kind": "feed"}
    if "html" not in content_type and b"<link" not in body[:4096].lower():
        raise ValueError("That URL is not a feed or an HTML page")
    found = extract_feed_links(body, final)
    if found:
        return {"feeds": found, "kind": "page"}
    # Nothing advertised: try the handful of conventional locations, stopping at the first hit.
    for path in COMMON_FEED_PATHS:
        candidate = final.split("#")[0].rstrip("/") + path
        try:
            _, _, probe = request_page(candidate, limit=64_000, timeout=6)
        except Exception:
            continue
        if looks_like_feed(probe):
            return {"feeds": [{"url": candidate, "title": ""}], "kind": "guessed"}
    return {"feeds": [], "kind": "page"}


MAX_DISCOVERY_BYTES = 512_000


def fetch_topic(phrase):
    """An interest ("fusion energy") expanded into a query feed and parsed into items."""
    url = TOPICS.topic_url(phrase)
    _, _, data = request_page(url, limit=2_000_000)
    return TOPICS.parse_topic_feed(data)
