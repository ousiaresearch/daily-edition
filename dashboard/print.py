"""Print pipeline: turn a composed edition into a page a printer can actually print.

The contract (see PRINT-PIPELINE.md) is four steps and no shell:

1. **render** — the caller supplies structured content; this module sets it as a broadsheet page
   (nameplate, dateline, lead, three columns, folio). Every string is escaped, so a headline
   cannot inject markup into the printed page, and no URL is ever printed as body text.
2. **paginate** — HTML becomes PDF through a headless browser when one is available (Chrome,
   Chromium, Edge). Without a browser the HTML is still written and a plain-text rendition is
   produced, because CUPS prints text fine and a silent failure is worse than a plain page.
3. **fit** — the paper is meant to be one page. If the PDF runs longer, stories are dropped from
   the tail and the page is rendered again, up to FIT_ATTEMPTS times.
4. **submit** — `lp` with an argument array and a printer name validated against the local queue
   list. No `shell=True`, no interpolation, no network.

Nothing here calls a model, and nothing is printed unless the caller asks (`dry_run`).
"""

import copy
import html
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
from urllib.parse import urlsplit

MAX_PAGES = 1
FIT_ATTEMPTS = 4
RENDER_TIMEOUT = 90

# The sheet is a local file and the renderer must not reach the network while drawing it: a headless
# browser will otherwise fetch component updates, sync data and phone home in the background, which
# would make "printing sends nothing over the network" untrue of the process as a whole.
BROWSER_FLAGS = [
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-sync',
    '--disable-extensions',
    '--metrics-recording-only',
    '--no-pings',
]
PRINTER_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')

URL_RE = re.compile(r'https?://\S+', re.I)
FEED_LABELS = re.compile(
    r'\b(article url|comments url|read more|continue reading|full story|source)\s*:?', re.I)
FEED_NOISE = re.compile(r'\b(points:\s*\d+|#\s*comments(?:\s*:\s*\d+)?|comments:\s*\d+)\b', re.I)

CHROME_CANDIDATES = (
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
)


def _load(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, pathlib.Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def subprocess_env():
    """Allow only OS settings needed by the browser and local CUPS tools, never credentials."""
    allowed = ('HOME', 'PATH', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'LC_CTYPE',
               'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'SYSTEMROOT', 'USERPROFILE')
    return {name: os.environ[name] for name in allowed if name in os.environ}


def outputs_dir():
    state = _load('state.py', 'daily_edition_state_print')
    path = state.home() / 'plugin-data' / 'daily-edition' / 'prints'
    path.mkdir(parents=True, exist_ok=True)
    return path


def chrome_path():
    override = os.environ.get('DAILY_EDITION_CHROME', '').strip()
    if override and pathlib.Path(override).exists():
        return override
    for candidate in CHROME_CANDIDATES:
        if pathlib.Path(candidate).exists():
            return candidate
    return ''


def _escape(value, limit=2000):
    return html.escape(str(value or '')[:limit], quote=True)


def clean_snippet(text, limit=520):
    """Publisher blurb → printable body copy.

    Feed descriptions are frequently link dumps ("Article URL: … Comments URL: … Points: 12").
    A newspaper prints prose, so URLs, feed labels and vote counts are removed; if what remains is
    not a sentence, the story prints as a headline with its source line instead of a stub.
    """
    value = str(text or '')
    value = URL_RE.sub(' ', value)
    value = FEED_LABELS.sub(' ', value)
    value = FEED_NOISE.sub(' ', value)
    value = re.sub(r'<[^>]+>', ' ', value)
    value = html.unescape(value)
    value = ' '.join(value.split())
    value = value.strip(' -·|–—,;:')
    if len(value) < 20:
        return ''
    if len(value) > limit:
        cut = value[:limit]
        end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
        value = (cut[:end + 1] if end > limit * 0.5 else cut.rsplit(' ', 1)[0]) + ' …'
    return value


def deck_of(text, limit=150):
    """The sentence a sub-editor would pull up under the lead headline."""
    body = clean_snippet(text, limit=limit)
    if not body:
        return ''
    end = body.find('. ')
    return body[:end + 1] if 0 < end < limit else body


def split_deck(text):
    """Lead copy → (deck, body). The deck is the first sentence; the body never repeats it."""
    value = clean_snippet(text, 900)
    if not value:
        return '', ''
    end = value.find('. ')
    if 0 < end < 220:
        rest = value[end + 2:].strip()
        return value[:end + 1], (rest if len(rest) >= 60 else '')
    return '', value


def domain_of(url):
    try:
        host = urlsplit(str(url or '')).hostname or ''
    except ValueError:
        return ''
    host = host.lower().removeprefix('www.')
    return host


CSS = """
@page { size: Letter; margin: 10mm 11mm 9mm 11mm; }
.sheet { zoom: 1; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; }
body {
  font-family: 'Iowan Old Style', 'Palatino Linotype', Palatino, 'Book Antiqua',
               'Times New Roman', serif;
  color: #111; margin: 0; font-size: 8.6pt; line-height: 1.32;
  font-kerning: normal; font-variant-ligatures: common-ligatures;
}
p { margin: 0; text-align: justify; hyphens: auto; }
h1, h2, h3 { text-wrap: balance; }
.nameplate { padding-top: 2pt; margin-bottom: 5pt; }
.rule-thick { border-top: 2.6pt solid #111; }
.rule-thin { border-top: .6pt solid #111; }
.kicker {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 6.4pt;
  letter-spacing: .22em; text-transform: uppercase; color: #333;
}
.nameplate h1 {
  font-family: 'Didot', 'Bodoni 72', 'Playfair Display', Georgia, serif;
  font-size: 44pt; line-height: .98; margin: 6pt 0 6pt; letter-spacing: -.015em;
  text-align: center; font-weight: 700;
}
.nameplate .kicker { text-align: center; }
.dateline {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8pt;
  border-top: .6pt solid #111; border-bottom: 2.6pt solid #111;
  padding: 2.5pt 0 2pt; margin-top: 4pt;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 6.6pt;
  letter-spacing: .12em; text-transform: uppercase;
}
.dateline .mid { letter-spacing: .2em; color: #444; }
.standfirst {
  font-style: italic; font-size: 8.8pt; text-align: center; color: #333;
  margin: 6pt 0 0; padding: 0 8mm;
}
.lead { border-bottom: 1.2pt solid #111; padding-bottom: 8pt; margin: 8pt 0 9pt; }
.lead .kicker { color: #111; border-bottom: .6pt solid #111; padding-bottom: 1.5pt; }
.lead h2 {
  font-size: 30pt; line-height: .98; margin: 3pt 0 4pt; letter-spacing: -.012em;
  text-align: left; font-weight: 700;
}
.lead .deck { font-size: 10.8pt; line-height: 1.26; font-style: italic; color: #333;
  margin: 0 0 5pt; text-align: left; max-width: 52ch; }
.byline {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 6.4pt;
  letter-spacing: .14em; text-transform: uppercase; color: #444; margin: 0 0 4pt;
}
.lead .body.short { column-count: 1; }
.lead .body { font-size: 9.6pt; line-height: 1.36; column-count: 2; column-gap: 6mm;
  column-rule: .4pt solid #b3b3b3; }
.columns { column-count: 3; column-gap: 6mm; column-rule: .4pt solid #b3b3b3;
  column-fill: balance; }
.story { break-inside: auto; margin-bottom: 8pt; }
.story h3 { break-inside: avoid; break-after: avoid; }
.story .body { orphans: 3; widows: 3; }
.story .source { break-before: avoid; }
.story .kicker { color: #555; font-size: 6pt; }
.story h3 { font-size: 12.6pt; line-height: 1.08; margin: 1.5pt 0 3pt; font-weight: 700; }
.story .body { font-size: 8.2pt; line-height: 1.3; }
.story .source {
  display: block; margin-top: 2pt; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 5.9pt; letter-spacing: .14em; text-transform: uppercase; color: #666;
}
.brief { break-inside: avoid; margin-bottom: 5pt; }
.brief h3 { font-size: 9.4pt; margin: 0 0 1pt; text-align: left; }
.empty { font-style: italic; color: #444; font-size: 9pt; text-align: center; margin: 12pt 0; }
footer {
  border-top: 1.2pt solid #111; margin-top: 7pt; padding-top: 3pt;
  display: flex; justify-content: space-between; gap: 8pt;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 5.9pt; letter-spacing: .08em; text-transform: uppercase; color: #555;
}
footer .note { text-transform: none; letter-spacing: 0; font-style: italic; }
"""


def render_html(edition, source_urls=None, scale=1.0):
    """A self-contained, print-styled broadsheet page for one edition.

    ``edition`` is the dict composed by edition.py (the tool side) — the same shape the page uses.
    ``scale`` is the typographic zoom the fitting loop settles on: it enlarges the whole sheet so a
    quiet news day still fills the page instead of leaving half of it blank.
    Empty editions still render: a masthead and an honest line beat a blank sheet.
    """
    lead = edition.get('lead') or {}
    number = int(edition.get('number') or 0)
    date_label = _escape(edition.get('dateLabel'))
    standfirst = _escape(edition.get('standfirst') or '', 400)
    story_count = edition.get('storyCount') or 0
    source_count = edition.get('sourceCount') or 0
    counts = ('%d %s · %d %s · %d cross-posted'
              % (story_count, 'story' if story_count == 1 else 'stories',
                 source_count, 'source' if source_count == 1 else 'sources',
                 edition.get('crossPosted') or 0))

    publishers = lambda story: story.get('publishers') or story.get('sources') or []

    def filed_by(story):
        names = publishers(story)
        # A byline is a claim about who wrote it; only cross-posted stories have more than one.
        return ('Reported by ' + ' and '.join(_escape(name, 60) for name in names)) if len(names) > 1 else ''

    domains = lambda story: ' · '.join(
        d for d in (domain_of(url) for url in publishers(story)) if d)
    single_source = source_count == 1

    lead_html = ''
    if lead:
        deck, lead_body = split_deck(lead.get('snippet'))
        lead_html = (
            '<section class="lead">'
            '<div class="kicker">Lead story</div>'
            '<h2>%s</h2>'
            '%s'
            '%s'
            '%s'
            '</section>'
            % (_escape(lead.get('title')),
               ('<p class="deck">%s</p>' % _escape(deck, 240)) if deck else '',
               ('<div class="byline">%s</div>' % filed_by(lead)) if filed_by(lead) else '',
               ('<p class="%s">%s</p>' % ('body short' if len(lead_body) < 320 else 'body',
                                          _escape(lead_body))) if lead_body else '')
        )

    entries, briefs_html = [], []
    for section in edition.get('sections') or []:
        for story in section.get('stories') or []:
            body = clean_snippet(story.get('snippet'))
            source_line = domains(story)
            if body:
                entries.append((story, body, source_line))
            else:
                # No prose worth setting: print it as a brief, the way a paper prints short items.
                briefs_html.append(
                    '<article class="brief"><h3>%s</h3>%s</article>'
                    % (_escape(story.get('title')),
                       ('<span class="source">%s</span>' % _escape(source_line, 120))
                       if source_line else '')
                )

    def story_html(index, entry):
        story, body, source_line = entry
        return (
            '<article class="story" data-story="s%d">'
            '<h3>%s</h3>'
            '<p class="body">%s</p>'
            '%s'
            '</article>'
            % (index, _escape(story.get('title')), _escape(body),
               ('<span class="source">%s</span>' % _escape(source_line, 120))
               if source_line else '')
        )

    columns_html = ''
    if entries:
        columns_html = '<div class="columns">%s</div>' % ''.join(
            story_html(index, entry) for index, entry in enumerate(entries)
        )
    if briefs_html:
        columns_html += (
            '<section class="briefs"><div class="kicker">In brief</div>%s</section>'
            % ''.join(briefs_html)
        )

    sources_line = ''
    if source_urls:
        seen = []
        for url in source_urls:
            host = domain_of(url)
            if host and host not in seen:
                seen.append(host)
        if seen:
            sources_line = 'Sources: ' + ' · '.join(_escape(host, 80) for host in seen[:10])

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Daily Edition No. %d — %s</title><style>%s</style></head><body>'
        '<div class="sheet" style="zoom: %.3f">'
        '<header class="nameplate">'
        '<div class="rule-thick"></div>'
        '<div class="kicker">A newspaper of your own</div>'
        '<h1>Daily Edition</h1>'
        '<div class="dateline"><span>No. %d</span>'
        '<span class="mid">%s</span><span>Compiled by Hermes</span></div>'
        '</header>'
        '%s'
        '%s'
        '%s'
        '<footer><span>Daily Edition · No. %d · page 1 of 1</span>'
        '<span class="note">%s</span>%s</footer>'
        '</div>'
        '<script id="measurement" type="application/json">{}</script>'
        '<script>(function(){var usable=984;var h=document.body.scrollHeight||0;'
        'var heights={};var nodes=document.querySelectorAll("article.story");'
        'for(var i=0;i<nodes.length;i++){heights[nodes[i].getAttribute("data-story")]='
        'Math.round(nodes[i].getBoundingClientRect().height);}'
        'var fill=h&&usable?Math.min(9.99,h/usable):0;'
        'if(fill){document.documentElement.setAttribute("data-fill",fill.toFixed(3));}'
        'var box=document.getElementById("measurement");'
        'if(box){box.textContent=JSON.stringify({fill:fill,heights:heights,count:nodes.length});}'
        '})();</script>'
        '</body></html>'
        % (number, date_label, CSS, scale,
           number, date_label,
           ('<p class="standfirst">%s</p>' % standfirst) if standfirst else '',
           lead_html,
           columns_html if columns_html else
           '<p class="empty">No stories were printed in this edition.</p>',
           number, _escape(counts, 200),
           ('<span>%s</span>' % sources_line) if sources_line else '')
    )


def render_pdf(html_text, out_path, html_path=''):
    """HTML → PDF through a local headless browser. Returns (path, error)."""
    chrome = chrome_path()
    if not chrome:
        return '', 'no headless browser found (set DAILY_EDITION_CHROME or install Chrome)'
    html_file = pathlib.Path(html_path or (str(out_path) + '.html'))
    html_file.parent.mkdir(parents=True, exist_ok=True)
    html_file.write_text(html_text, encoding='utf-8')
    try:
        completed = subprocess.run(
            [chrome, '--headless=new', *BROWSER_FLAGS,
             '--no-pdf-header-footer', '--virtual-time-budget=2000',
             '--print-to-pdf=%s' % out_path, 'file://%s' % html_file],
            capture_output=True, timeout=RENDER_TIMEOUT, env=subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return '', 'browser failed: %s' % exc
    if not pathlib.Path(out_path).exists():
        tail = (completed.stderr or b'')[-400:].decode('utf-8', 'replace')
        return '', 'browser produced no PDF: %s' % (tail or 'unknown error')
    return str(out_path), ''


def page_count(pdf_path):
    """Pages in a PDF, counted from its page objects (no PDF library required)."""
    try:
        data = pathlib.Path(pdf_path).read_bytes()
    except OSError:
        return 0
    return len(re.findall(rb'/Type\s*/Page(?!s)', data))


def to_text(html_text):
    """A plain-text rendition, for CUPS queues with no PDF filter and for eyeballing."""
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html_text, flags=re.S | re.I)
    text = re.sub(r'</(div|p|h1|h2|h3|h4|section|article|header|footer)>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    lines = [' '.join(line.split()) for line in text.splitlines()]
    return '\n'.join(line for line in lines if line) + '\n'


def available_printers():
    """Local CUPS destinations, or [] when CUPS has none configured."""
    lpstat = shutil.which('lpstat')
    if not lpstat:
        return []
    try:
        completed = subprocess.run([lpstat, '-p'], capture_output=True, timeout=15, text=True, env=subprocess_env())
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r'^printer\s+(\S+)', completed.stdout or '', flags=re.M)


def submit(path, printer=''):
    """Send a file to a printer with an argument array. Returns (job_id, error)."""
    printer = (printer or '').strip()
    # Validate the caller's input before asking the host anything: a malformed name is a caller
    # bug on every machine, and the error should not change with the host's CUPS install.
    if printer and not PRINTER_RE.match(printer):
        return '', 'Invalid printer name'
    lp = shutil.which('lp')
    if not lp:
        return '', 'CUPS lp is not installed'
    known = available_printers()
    if printer and known and printer not in known:
        return '', 'No such printer: %s (available: %s)' % (printer, ', '.join(known) or 'none')
    if not printer and not known:
        return '', 'No printer is configured on this machine'
    command = [lp] + (['-d', printer] if printer else []) + [str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=30, text=True, env=subprocess_env())
    except (OSError, subprocess.SubprocessError) as exc:
        return '', 'lp failed: %s' % exc
    if completed.returncode != 0:
        return '', (completed.stderr or completed.stdout or 'lp failed').strip()[:300]
    match = re.search(r'request id is (\S+)', completed.stdout or '')
    return (match.group(1) if match else 'submitted'), ''


TARGET_FILL = 0.94
MAX_SCALE = 1.55
MAX_ATTEMPTS = 8


def measure_layout(html_path):
    """Ask the page how tall it is and how tall each story is (fill, heights in px)."""
    chrome = chrome_path()
    if not chrome:
        return {'fill': 0.0, 'heights': {}, 'count': 0}
    try:
        completed = subprocess.run(
            [chrome, '--headless=new', *BROWSER_FLAGS, '--hide-scrollbars', '--window-size=733,1056',
             '--virtual-time-budget=800', '--dump-dom', 'file://%s' % html_path],
            capture_output=True, text=True, timeout=45, env=subprocess_env())
    except (OSError, subprocess.SubprocessError):
        return {'fill': 0.0, 'heights': {}, 'count': 0}
    dom = completed.stdout or ''
    match = re.search(r'<script id="measurement"[^>]*>(.*?)</script>', dom, re.S)
    if match:
        try:
            payload = json.loads(match.group(1) or '{}')
            return {'fill': float(payload.get('fill') or 0.0),
                    'heights': {str(k): float(v) for k, v in (payload.get('heights') or {}).items()},
                    'count': int(payload.get('count') or 0)}
        except (ValueError, TypeError):
            pass
    fill = re.search(r'data-fill="([0-9.]+)"', dom)
    return {'fill': float(fill.group(1)) if fill else 0.0, 'heights': {}, 'count': 0}


def print_edition(edition, printer='', dry_run=False, max_pages=MAX_PAGES, source_urls=None):
    """Typeset, fit to one page, and (unless dry_run) print. Never raises for a printer problem.

    Two things are being fitted, in this order: the sheet must be one page, and it should not be
    half empty. If the type is small enough to leave the page under-filled the whole sheet is
    enlarged; if it overflows, the enlargement is backed off before any story is dropped.
    """
    stamp = time.strftime('%Y%m%d-%H%M%S')
    base = outputs_dir() / ('No%s-%s' % (edition.get('number') or 1, stamp))
    html_path = str(base) + '.print.html'
    attempts = []
    trimmed = dict(edition)
    scale = 1.0
    page_html, pdf_path, pdf_error = '', '', ''
    best = None
    last_good = None
    bisected = False

    try_files = []
    for attempt in range(MAX_ATTEMPTS):
        page_html = render_html(trimmed, source_urls=source_urls, scale=scale)
        pathlib.Path(html_path).write_text(page_html, encoding='utf-8')
        # One PDF per attempt: the file finally submitted is a copy of the measured one, never a
        # path that a later render has since overwritten.
        attempt_pdf = '%s-try%d.pdf' % (base, attempt + 1)
        try_files.append(attempt_pdf)
        pdf_path, pdf_error = render_pdf(page_html, attempt_pdf, html_path=html_path)
        pages = page_count(pdf_path) if pdf_path else 0
        layout = measure_layout(html_path) if pdf_path and pages <= max_pages else {'fill': 0.0, 'heights': {}}
        fill = layout.get('fill') or 0.0
        attempts.append({'stories': trimmed.get('storyCount') or 0, 'pages': pages,
                         'fill': round(fill, 3), 'scale': round(scale, 3), 'attempt': attempt + 1})
        if pdf_path and pages <= max_pages:
            last_good = scale
            best = {'html': page_html, 'pdf': pdf_path, 'stories': trimmed.get('storyCount') or 0,
                    'storyList': list(trimmed.get('stories') or []), 'scale': scale,
                    'heights': layout.get('heights') or {},
                    'pages': pages, 'fill': fill, 'error': pdf_error}
            if fill >= TARGET_FILL:
                break
        if not pdf_path:
            break
        if pages > max_pages:
            # We only enlarge after a render that fitted, so an overflow means the previous
            # attempt was the largest sheet that fits. One bisection closes most of the gap
            # between "fills 89%" and "spills onto a second page"; after that, stop.
            if scale > 1.0:
                if last_good is not None and not bisected and scale - last_good > 0.02:
                    scale = round((last_good + scale) / 2, 3)
                    bisected = True
                    continue
                break
            stories = list(trimmed.get('stories') or [])
            if len(stories) <= 1:
                break
            keep = max(1, min(len(stories) - 1, int(len(stories) * 0.8)))
            trimmed = dict(trimmed, stories=stories[:keep], storyCount=keep,
                           omitted=(trimmed.get('omitted') or 0) + (len(stories) - keep))
            continue
        # Fits but under-filled: enlarge the sheet.
        if scale >= MAX_SCALE:
            break
        scale = min(MAX_SCALE, round(scale * 1.15, 3))

    final_pdf = ''
    if best:
        page_html = best['html']
        trimmed = dict(trimmed, storyCount=best['stories'], stories=best['storyList'])
        final_pdf = str(base) + '.pdf'
        try:
            shutil.copyfile(best['pdf'], final_pdf)
        except OSError:
            final_pdf = best['pdf']
    elif pdf_path:
        final_pdf = pdf_path
    pdf_path = final_pdf
    for leftover in try_files:
        if pathlib.Path(leftover).exists() and leftover != pdf_path:
            pathlib.Path(leftover).unlink()
    pathlib.Path(html_path).write_text(page_html, encoding='utf-8')
    text_path = str(base) + '.txt'
    pathlib.Path(text_path).write_text(to_text(page_html), encoding='utf-8')

    result = {
        'ok': True,
        'dryRun': bool(dry_run),
        'html': html_path,
        'pdf': pdf_path,
        'text': text_path,
        'pages': page_count(pdf_path) if pdf_path else 0,
        'fill': round(best['fill'], 3) if best else 0.0,
        'stories': trimmed.get('storyCount') or 0,
        'attempts': attempts,
        'error': pdf_error if not pdf_path else '',
        'printer': '',
        'job': '',
    }
    if dry_run:
        return result
    submitted, submit_error = submit(pdf_path or text_path, printer)
    result['printer'] = printer or '(default)'
    result['job'] = submitted
    if submit_error:
        result['ok'] = False
        result['error'] = submit_error
    return result
