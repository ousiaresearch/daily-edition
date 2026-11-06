"""Interests → topic feeds.

An interest is a phrase ("fusion energy", "Málaga housing"), not a subscription. It is expanded
into a query feed, fetched, and the results become that interest's section of the edition.

The default provider is Google News RSS: public, keyless, and explicitly restricted to personal,
non-commercial use in a feed reader. Callers must not present it as a general-purpose news API.
"""

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlsplit

DEFAULT_PROVIDER = 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'

_PUBLISHER_SUFFIX = re.compile(r'\s+-\s+([^-]{2,60})$')


def topic_url(query, provider=DEFAULT_PROVIDER):
    phrase = str(query or '').strip()
    if not phrase:
        raise ValueError('An interest needs some words')
    if len(phrase) > 120:
        raise ValueError('Interest is too long')
    return provider.format(query=quote_plus(phrase))


def _split_publisher(title):
    """Google News appends ' - Publisher' to every title; strip it when it looks like one."""
    match = _PUBLISHER_SUFFIX.search(title)
    if not match:
        return title, ''
    head = title[:match.start()].strip()
    if len(head) < 12:  # a short head is more likely a real dash than a masthead
        return title, ''
    return head, match.group(1).strip()


def parse_topic_feed(data, base='https://news.google.com/'):
    if isinstance(data, str):
        data = data.encode('utf-8', 'replace')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported XML declaration')
    root = ET.fromstring(data)
    channel = root.find('channel')
    if channel is None:
        raise ValueError('Not an RSS topic feed')
    items, seen = [], set()
    for node in channel.findall('item')[:100]:
        link = (node.findtext('link') or '').strip()
        parts = urlsplit(link)
        if parts.scheme not in ('http', 'https') or not parts.hostname or link in seen:
            continue
        seen.add(link)
        raw_title = ' '.join((node.findtext('title') or '').split())
        if not raw_title:
            continue
        source = node.find('source')
        publisher = ' '.join((source.text or '').split()) if source is not None else ''
        title, suffix = _split_publisher(raw_title)
        items.append({
            'title': title,
            'url': link,
            'snippet': ' '.join((node.findtext('description') or '').split())[:400],
            'date': ' '.join((node.findtext('pubDate') or '').split()),
            'publisher': publisher or suffix,
        })
    return {'source': ' '.join((channel.findtext('title') or '').split()), 'items': items}
