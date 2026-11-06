# Print pipeline — v1 spec

**Status:** implemented in Daily Edition 0.4.0 (`dashboard/print.py`) and verified on macOS.
**Scope:** any Hermes plugin that composes content meant to leave the screen.

A plugin that can render a page can put it on paper. The pipeline is deliberately small: four
steps, one data shape, no shell, no network, no model.

---

## 1. Input shape (`edition/v1`)

The renderer takes one JSON object. Extra keys are ignored; missing keys degrade to an honest
empty page rather than an error.

```json
{
  "number": 4,
  "dateLabel": "Thursday, 5 November 2026",
  "standfirst": "7 new since No. 3 · 2 still running",
  "storyCount": 9, "sourceCount": 3, "crossPosted": 2, "withheld": 1, "omitted": 0,
  "lead": { "title": "…", "snippet": "…", "publishers": ["Alpha"], "url": "https://…" },
  "sections": [
    { "source": "Beta", "stories": [
      { "title": "…", "snippet": "…", "publishers": ["Beta"], "url": "https://…" }
    ] }
  ]
}
```

Rules the renderer enforces, whatever the caller passes:

- **Every string is escaped.** A headline is text; it is never markup. Titles that contain `<`,
  `&` or quotes print literally.
- **Nothing from the network is fetched.** The renderer draws only the object it is given.
- **Snippets are capped** (900 chars for the lead, 600 for a story) so one long description cannot
  push the page over.

## 2. Steps

1. **Render** — self-contained HTML with `@page` geometry, a serif body, a double-ruled masthead
   and a footer carrying the edition number, date and sources. No external CSS, fonts or images.
2. **Paginate** — HTML → PDF through a local headless browser (Chrome, Chromium or Edge). The
   browser path is discoverable (`DAILY_EDITION_CHROME`) and never downloaded.
3. **Typeset and fit** — the page is meant to be **one sheet that looks like a newspaper**, so two
   things are fitted, in this order:
   - **Fill.** The page measures itself (`data-fill` = document height ÷ printable height, read back
     through the headless browser) and the whole sheet is enlarged in 15% steps until it covers
     about 94% of the page, so a quiet news day sets in larger type instead of leaving half the
     sheet blank.
   - **Pages.** If the enlargement overflows onto a second page, one bisection step is taken between
     the largest fitting scale and the overflow, and the loop settles on the largest scale that still
     fits. Only when the base size overflows are stories dropped — tail first, about 20% at a time.
     The count is reported, and a page that still runs long is submitted rather than silently
     truncated.
   Every attempt renders to its own PDF; the file finally submitted is a copy of the attempt that was
   measured, never a path a later render has overwritten.
4. **Submit** — `lp` with an **argument array** and a printer name validated against the local
   queue list. No `shell=True`, no interpolation, no printer discovered from the network.

## 3. Artifacts and response

Every render leaves three files under `$HERMES_HOME/daily-edition/prints/`:

| File | Purpose |
|---|---|
| `No<n>-<stamp>.print.html` | the page, openable in any browser |
| `No<n>-<stamp>.pdf` | what is submitted (may be absent if no browser is installed) |
| `No<n>-<stamp>.txt` | a plain-text rendition, printable by any CUPS queue |

Response:

```json
{ "ok": true, "dryRun": false, "pages": 1, "stories": 9,
  "printer": "Office", "job": "Office-42",
  "html": "…", "pdf": "…", "text": "…",
  "attempts": [{"stories": 9, "pages": 1, "fill": 0.896, "scale": 1.15, "attempt": 2}],
  "error": "" }
```

`scale` is the typographic zoom of the submitted sheet and `fill` the fraction of the page it
covers, so a caller can tell a full sheet from a quiet one without opening the PDF.

`ok:false` always carries a human `error` and still leaves the artifacts behind, so a user with no
printer can print the file themselves.

## 4. Failure semantics

| Situation | Behaviour |
|---|---|
| No headless browser | PDF absent, `error` names it, HTML + text still written, submission uses the text file |
| No CUPS queue | `ok:false`, `"No printer is configured on this machine"`, files left for manual printing |
| Unknown printer name | `ok:false` listing the queues that do exist — never a silent fallback to another printer |
| `lp` fails | `ok:false` with `lp`'s stderr, truncated to 300 chars |
| Long page | stories dropped from the tail; the count is reported in `attempts` and `stories` |

## 5. Security boundaries

- Printer names match `^[A-Za-z0-9._-]{1,64}$` before they reach `lp`.
- The browser runs on a `file://` URL under the profile's own prints directory, with a timeout.
- Output paths are built from the edition number and a timestamp — no user-supplied path segment.
- The pipeline writes only under `$HERMES_HOME/daily-edition/prints/`.

## 6. Adopting it from another plugin

1. Build the `edition/v1` object (or reuse Daily Edition's `dashboard/edition.py` composer).
2. Call `print_edition(payload, printer=…, dry_run=…)` — import by path, exactly as Daily Edition
   does, or shell out to the plugin's own `/print` route.
3. Expose a `dry_run` path in your UI before the real one. A page nobody previewed is a page nobody
   trusts.
4. Add one line to your disclosure: what is printed, to which queue, and what stays on disk.

## 7. What is not in v1

- Colour, images, QR codes (deliberately: a reading copy, not a facsimile).
- Multi-page layout and page furniture beyond the footer.
- Duplex, tray or media selection — pass them through as future `options` keys, not by growing the
  core.
- Label printers, 3D printers and photo printers: different pipeline, different guarantees.

---

## Verification record

- 22 unit tests (`tests/test_print.py`): escaping, no URLs printed, link dumps becoming briefs,
  broadsheet structure, empty edition, page counting, printer validation, no-shell invocation,
  job-id parsing, fill growth, overflow bisection, printer failure paths.
- One real Chrome render per run when Chrome is present (`RealPdfTests`).
- One live end-to-end dry run against `https://hnrss.org/frontpage`: link-dump descriptions reduced to
  headlines and briefs (no URLs printed), rendered to a **1-page** Letter PDF, no source errors.
- One typeset run from a synthetic three-source edition: 9 stories, three columns, fill 89.6% at
  scale 1.15 after one bisection, one page, no story dropped — inspected as an image: no split
  headlines, no orphaned headings.
- **Not verified on this machine:** actual submission through CUPS — `lpstat -p` reports no
  destinations, so the `lp` path is covered by tests with a mocked queue, not by a printed sheet.
