# Changelog

All notable changes to Daily Edition. Versions follow the plugin manifest (`plugin.yaml`), which is
kept in step with `dashboard/manifest.json` by a test.

## 0.4.7 — 2026-11-06

### Changed
- **The styling key is read through Hermes, not from the environment.** `settings()` now asks
  `agent.secret_scope.get_secret('DAILY_EDITION_API_KEY')` first and fails closed when a scope is
  active but holds no value, because under profile multiplexing a bare `os.environ` read can pick up
  another profile's key. This is catalog rule 11, and the previous code broke it.
- A **2:1 hero card** (`docs/images/hero-card.png`/`.jpg`, 1600×800) for catalog listings, generated
  from the same brief and script as the 16:9 README hero — the entry's `image:` field is specified at
  2:1 and the 16:9 version would have been cropped.

## 0.4.6 — 2026-11-06

### Changed
- **Styling no longer defaults to a third-party endpoint.** `DAILY_EDITION_BASE_URL` has no default:
  the editorial voices stay off until you name an OpenAI-compatible endpoint. A public plugin must not
  route a stranger's headlines to a vendor nobody chose, and the previous default pointed at one.
  `settings()` now reports the missing endpoint by name; `DAILY_EDITION_MODEL` still defaults.

### Fixed
- The headless renderer is launched with background networking disabled (`--disable-background-networking`,
  `--disable-component-update`, `--disable-sync`, `--no-pings`, no default apps or extensions) for both
  the print and the measurement pass, so a print really does not reach the network. Found by the
  catalog admission review, which noticed the browser could still phone home while the plugin could not.

## 0.4.5 — 2026-11-06

### Fixed
- The packaging suite no longer assumes the checkout directory is named `daily-edition`: it reads the
  `origin` remote (and skips when there is none) and separately asserts the name is a valid plugin
  slug. Before this, a reviewer cloning into `/tmp/pincheck` got one red test in a suite that had
  nothing to do with the change. Found at the pinned commit during plugin-catalog pre-flight.

## 0.4.4 — 2026-11-06

### Added
- The release hero (`docs/images/hero.jpg`), built reproducibly from `docs/hero/prompt.txt` and
  `docs/hero/build.py`: a generated print still life with no legible text, every word set as vector
  type over it, with a second plate a hair off so the type reads as printed.
- `docs/corrections.md`, recording the commit-identity rewrite and what remains visible afterwards.

### Changed
- No behaviour change. This release exists so the plugin catalog entry can pin a commit that carries
  the card art, the corrections log and an honest install section.

## 0.4.3 — 2026-11-06

### Fixed
- `submit()` now validates the printer name **before** probing the host, so a malformed name reports
  `Invalid printer name` on every machine instead of `CUPS lp is not installed` where CUPS is absent.
- The print tests no longer depend on the host having CUPS: binaries are resolved through a patched
  `shutil.which`, and a new test covers the "no CUPS at all" message. First CI run on Linux caught
  six portability failures that macOS hid; this is that fix.

## 0.4.2 — 2026-11-05

### Changed
- **One story, once, properly.** Clustering was headline-token Jaccard at 0.6, which printed the same
  event twice when two outlets worded it differently. It now matches on a canonical link, shared
  wording, a shared named phrase ("transit plan") with a compatible verb, or headline containment —
  with a contradictory-verb veto (*approved* never merges with *delayed*), a conflicting-year veto,
  and a same-publisher guard so a masthead cannot cross-post itself. Clusters merge transitively.
- **Columns end level.** Body copy flows across the three columns with headlines protected from
  splitting (`break-inside: avoid; break-after: avoid`), `orphans/widows: 3`, and
  `column-fill: balance`, so the bottoms meet at one rule instead of leaving a ragged foot.
- The clustering rules are implemented in both engines (`desktop/edition.js`, `dashboard/edition.py`)
  and pinned by parity fixtures that run the same pairs through both.

## 0.4.1 — 2026-11-05

### Added
- Broadsheet typesetting for the printed sheet: ruled nameplate, three-part dateline, lead story with
  deck, three columns with column rules, an **In brief** column for items without prose, and a folio
  naming the edition and its sources.
- The page measures its own height and enlarges the whole sheet until it covers ~94% of the page; an
  overflow is bisected back to the largest size that still fits before any story is dropped.

### Changed
- Feed noise is stripped before setting: URLs, `Article URL:`/`Comments URL:` labels and
  `Points: N # Comments: N`. No URL is printed as body text; publisher domains appear in small caps.
- Every print attempt renders to its own PDF, and the file submitted is a copy of the measured one.

## 0.4.0 — 2026-11-05

### Added
- **Print pipeline** (`dashboard/print.py`, [PRINT-PIPELINE.md](PRINT-PIPELINE.md)): HTML → headless
  Chrome/Chromium/Edge → one-page PDF → CUPS `lp`, with an argument array, a validated printer name
  and no shell.
- "Print the paper" button, `daily_edition` action `print_paper` (with `dry_run`), and
  `/edition paper` / `/edition preview`.
- Artifacts are always left behind (HTML, PDF, plain text) when a printer is missing or fails.

## 0.3.0 — 2026-11-05

### Added
- **Reading in the paper**: a reader pane that fetches the article and renders it as typed text
  blocks (headings, paragraphs, list items, quotations) — no publisher HTML reaches the renderer.
- Unread / Saved / All views, search, and keyboard control: `j`/`k`, `Enter`, `s`, `r`, `/`, `u`, `Esc`.
- **Offline paper**: the last composed edition is stored and used as the first paint and as the
  fallback when no source can be reached, with an *as of* stamp.
- **OPML export**, round-tripping through the importer.
- **Agent surface**: the `daily_edition` tool (print / diff / sources) and the `/edition` command,
  composed by a Python port of the edition model held to the JavaScript by a parity test; a bundled
  skill with a tested cron recipe for a weekday morning print.
- Packaging: MIT `LICENSE`, git history, `requires_hermes`, `provides_tools`, rewritten README and
  [PRINT-PIPELINE.md](PRINT-PIPELINE.md).

### Changed
- Redirects are followed up to three hops, each hop re-vetted by the same SSRF rules.
- The page mirrors its settings to `$HERMES_HOME/daily-edition/state.json` (0600, atomic replace).

## 0.2.0 — pre-release

- Interests expanded into query feeds, dated editions, cross-source consensus, reprint suppression,
  seven back issues, editorial voices with a fidelity guard, OPML import, feed discovery.
