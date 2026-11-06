"""Print pipeline: turn a composed edition into a page a printer can actually print.

The contract (see PRINT-PIPELINE.md) is four steps and no shell:

1. **render** — the caller supplies structured content; this module renders self-contained HTML.
   Every string is escaped, so a headline cannot inject markup into the printed page.
2. **paginate** — HTML becomes PDF through a headless browser when one is available (Chrome,
   Chromium, Edge). Without a browser the HTML is still written and a plain-text rendition is
   produced, because CUPS prints text fine and a silent failure is worse than a plain page.
3. **fit** — the paper is meant to be one page. If the PDF runs longer, stories are dropped from
   the tail and the page is rendered again, up to FIT_ATTEMPTS times.
4. **submit** — `lp` with an argument array and a printer name validated against the local queue
   list. No `shell=True`, no interpolation, no network.

Nothing here calls a model, and nothing is printed unless the caller asks (`dry_run`).
"""

import html
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import time

MAX_PAGES = 1
FIT_ATTEMPTS = 4
RENDER_TIMEOUT = 90
PRINTER_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')

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


def outputs_dir():
    state = _load('state.py', 'daily_edition_state_print')
    path = state.home() / 'daily-edition' / 'prints'
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


CSS = """
@page { size: Letter; margin: 13mm 12mm 11mm 12mm; }
* { box-sizing: border-box; }
body { font-family: Georgia, 'Times New Roman', serif; color: #111; margin: 0; font-size: 9pt; }
.masthead { border-bottom: 3px double #111; padding-bottom: 6pt; margin-bottom: 8pt; }
.kicker { font-family: Helvetica, Arial, sans-serif; font-size: 7pt; letter-spacing: .18em;
          text-transform: uppercase; color: #444; }
h1 { font-size: 34pt; line-height: .95; margin: 4pt 0 2pt; letter-spacing: -.01em; }
.date { font-size: 8.5pt; color: #444; }
.standfirst { font-style: italic; font-size: 9pt; color: #333; margin: 3pt 0 0; }
.counts { font-family: Helvetica, Arial, sans-serif; font-size: 7pt; color: #555; margin-top: 2pt; }
.lead { border-top: 1pt solid #111; border-bottom: 1pt solid #111; padding: 6pt 0; margin-bottom: 8pt; }
.byline { font-family: Helvetica, Arial, sans-serif; font-size: 6.6pt; letter-spacing: .12em;
          text-transform: uppercase; color: #444; }
.lead h2 { font-size: 22pt; line-height: 1.05; margin: 2pt 0 3pt; }
.lead p { font-size: 9.7pt; line-height: 1.32; margin: 0; max-width: 68ch; overflow-wrap: anywhere; }
section { margin-bottom: 9pt; }
section h3 { font-family: Helvetica, Arial, sans-serif; font-size: 7pt; letter-spacing: .16em;
             text-transform: uppercase; border-bottom: .5pt solid #999; padding-bottom: 1.5pt; margin: 0 0 3pt; }
article { margin-bottom: 6.5pt; break-inside: avoid; }
article h4 { font-size: 11.4pt; line-height: 1.18; margin: 0 0 1.5pt; font-weight: 600; }
article p { font-size: 8.9pt; line-height: 1.28; margin: 0; color: #222; overflow-wrap: anywhere; }
footer { border-top: .5pt solid #999; margin-top: 8pt; padding-top: 3pt;
         font-family: Helvetica, Arial, sans-serif; font-size: 6.2pt; color: #666; }
"""


def render_html(edition, source_urls=None):
    """A self-contained, print-styled HTML page for one edition.

    ``edition`` is the dict composed by edition.py (the tool side) — the same shape the page uses.
    Empty editions still render: a masthead and an honest line beat a blank sheet.
    """
    lead = edition.get('lead') or {}
    number = int(edition.get('number') or 0)
    date_label = _escape(edition.get('dateLabel'))
    standfirst = _escape(edition.get('standfirst') or '', 400)
    counts = ('%d %s · %d %s · %d cross-posted · %d withheld'
              % (edition.get('storyCount') or 0,
                 'story' if (edition.get('storyCount') or 0) == 1 else 'stories',
                 edition.get('sourceCount') or 0,
                 'source' if (edition.get('sourceCount') or 0) == 1 else 'sources',
                 edition.get('crossPosted') or 0, edition.get('withheld') or 0))

    def byline(story, section_source=''):
        names = story.get('publishers') or story.get('sources') or []
        # One masthead, printed once: the section header already names a single-source story.
        if section_source and len(names) == 1 and names[0] == section_source:
            return ''
        return ' · '.join(_escape(name, 80) for name in names)

    sections = edition.get('sections') or []
    single_source = (edition.get('sourceCount') or 0) == 1

    lead_html = ''
    if lead:
        lead_byline = '' if single_source else byline(lead)
        lead_html = (
            '<div class="lead">%s'
            '<h2>%s</h2><p>%s</p></div>'
            % (('<div class="byline">%s</div>' % lead_byline) if lead_byline else '',
               _escape(lead.get('title')), _escape(lead.get('snippet'), 900))
        )

    sections_html = []
    for section in sections:
        articles = []
        # A one-source edition has nothing to disambiguate: print the masthead once, not above
        # every story.
        header = '' if single_source else '<h3>%s</h3>' % _escape(section.get('source'), 80)
        for story in section.get('stories') or []:
            filed_by = byline(story, section.get('source'))
            articles.append(
                '<article>%s<h4>%s</h4><p>%s</p></article>'
                % (('<div class="byline">%s</div>' % filed_by) if filed_by else '',
                   _escape(story.get('title')), _escape(story.get('snippet'), 600))
            )
        sections_html.append('<section>%s%s</section>' % (header, ''.join(articles)))

    sources_line = ''
    if source_urls:
        unique = sorted({str(url) for url in source_urls if url})[:14]
        sources_line = 'Sources: ' + ' · '.join(_escape(url, 120) for url in unique)

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<title>Daily Edition No. %d — %s</title><style>%s</style></head><body>'
        '<div class="masthead"><div class="kicker">A newspaper of your own</div>'
        '<h1>Daily Edition</h1><div class="date">No. %d · %s</div>'
        '%s<div class="counts">%s</div></div>'
        '%s'
        '%s'
        '<footer>No. %d · %s · Printed by Hermes · %s · every story links to its publisher; this '
        'page is a reading copy, not a reprint.</footer>'
        '</body></html>'
        % (number, date_label, CSS, number, date_label,
           ('<p class="standfirst">%s</p>' % standfirst) if standfirst else '',
           _escape(counts, 200),
           lead_html,
           ''.join(sections_html) if sections_html else
           '<p style="font-size:9pt;color:#444">No stories were printed in this edition.</p>',
           number, date_label, sources_line)
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
            [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
             '--no-pdf-header-footer', '--virtual-time-budget=2000',
             '--print-to-pdf=%s' % out_path, 'file://%s' % html_file],
            capture_output=True, timeout=RENDER_TIMEOUT,
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
    text = re.sub(r'</(div|p|h1|h2|h3|h4|section|article|footer)>', '\n', text, flags=re.I)
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
        completed = subprocess.run([lpstat, '-p'], capture_output=True, timeout=15, text=True)
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r'^printer\s+(\S+)', completed.stdout or '', flags=re.M)


def submit(path, printer=''):
    """Send a file to a printer with an argument array. Returns (job_id, error)."""
    lp = shutil.which('lp')
    if not lp:
        return '', 'CUPS lp is not installed'
    printer = (printer or '').strip()
    if printer and not PRINTER_RE.match(printer):
        return '', 'Invalid printer name'
    known = available_printers()
    if printer and known and printer not in known:
        return '', 'No such printer: %s (available: %s)' % (printer, ', '.join(known) or 'none')
    if not printer and not known:
        return '', 'No printer is configured on this machine'
    command = [lp] + (['-d', printer] if printer else []) + [str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=30, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return '', 'lp failed: %s' % exc
    if completed.returncode != 0:
        return '', (completed.stderr or completed.stdout or 'lp failed').strip()[:300]
    match = re.search(r'request id is (\S+)', completed.stdout or '')
    return (match.group(1) if match else 'submitted'), ''


def print_edition(edition, printer='', dry_run=False, max_pages=MAX_PAGES, source_urls=None):
    """Render, fit to one page, and (unless dry_run) print. Never raises for a printer problem."""
    stamp = time.strftime('%Y%m%d-%H%M%S')
    base = outputs_dir() / ('No%s-%s' % (edition.get('number') or 1, stamp))
    html_path = str(base) + '.print.html'
    attempts = []
    trimmed = dict(edition)
    page_html, pdf_path, pdf_error = '', '', ''

    # Render, look at the page count, drop the tail story, render again. The PDF that is finally
    # submitted always corresponds to the content that was measured, never to a stale attempt.
    for attempt in range(FIT_ATTEMPTS + 1):
        page_html = render_html(trimmed, source_urls=source_urls)
        pdf_path, pdf_error = render_pdf(page_html, str(base) + '.pdf', html_path=html_path)
        pages = page_count(pdf_path) if pdf_path else 0
        attempts.append({'stories': trimmed.get('storyCount') or 0, 'pages': pages,
                         'attempt': attempt + 1})
        stories = list(trimmed.get('stories') or [])
        if not pdf_path or pages <= max_pages or len(stories) <= 1:
            break
        # Trim proportionally: one story at a time cannot close a two-page overflow.
        keep = max(1, min(len(stories) - 1, int(len(stories) * 0.8)))
        trimmed = dict(trimmed, stories=stories[:keep], storyCount=keep,
                       omitted=(trimmed.get('omitted') or 0) + (len(stories) - keep))

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
