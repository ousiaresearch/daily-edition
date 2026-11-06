# Daily Edition — competitive audit

**Date:** 2026-11-05 (EST)
**Subject:** `daily-edition` 0.2.0 — `/Users/johannross/daily-edition`
**Comparators:** the five catalog desktop plugins that occupy the same "news in Hermes Desktop" space, plus the closest non-desktop ritual product.
**Method:** read the subject's source (1,408 lines: 480-line `desktop/plugin.js`, 254-line `desktop/edition.js`, 674 lines of backend Python), ran its suites and the Hermes validators, then compared against each competitor's pinned catalog README and repo tree at the catalog SHA (`~/.hermes/cache/plugin-catalog.json`, generated 2026-11-06T01:56Z).

---

## 1. Market position

The curated catalog holds **1,063 plugins**, of which **226 are `desktop`** (225 community, 1 official). Fifteen desktop entries touch news, feeds or reading; five are direct contenders:

| Plugin | Shape | Version |
|---|---|---|
| `rss-reader` | Three-column reader, folders, reader-mode capture, `rss` toolset + `/rss` commands | 1.1.0 |
| `rss-lite` | Lightweight reader: folders, unread/saved, OPML in/out, auto-refresh | 1.0.0 |
| `hermes-newswire` | Scrolling ticker strip + newswire page, offline SQLite cache | 0.1.0 (catalog, unreleased version field) |
| `hermes-rss` | Single-file reader (~175 KB `plugin.js`), AI grading | 0.0.5 |
| `hermes-blogwatcher` | Blogwatcher CLI-backed inbox, agent tools | 0.2.0 |
| `morning-briefing` | Cron-rendered printable newsprint page (automation category) | unpinned |

Daily Edition is **none of these**. It is the only product in the set whose unit of work is a *dated edition* rather than a feed or an article. That is a real category of one — and it is also why it currently loses on the table stakes every reader in the list already ships.

---

## 2. Scorecard

Weights reflect what decides adoption in this category: differentiated value 20, reading depth 15, distribution 15, freshness 10, personalisation 10, Hermes integration 10, robustness 10, polish 10.

| Plugin | Weighted (of 5) | Index |
|---|---|---|
| `rss-reader` | 4.05 | 81 |
| `rss-lite` | 3.90 | 78 |
| `hermes-newswire` | 3.75 | 75 |
| `hermes-rss` | 3.50 | 70 |
| `morning-briefing` | 3.40 | 68 |
| **`daily-edition`** | **3.05** | **61** |

Per-dimension (1–5):

| | Diff | Reading | Freshness | Personal | Integration | Distribution | Robustness | Polish |
|---|---|---|---|---|---|---|---|---|
| daily-edition | **5** | 2 | 2 | 3 | 3 | **1** | 4 | 4 |
| rss-reader | 2 | 5 | 4 | 5 | 5 | 4 | 4 | 5 |
| rss-lite | 2 | 5 | 5 | 4 | 3 | 5 | 4 | 4 |
| hermes-newswire | 3 | 3 | 5 | 3 | 4 | 4 | 5 | 4 |
| hermes-rss | 2 | 4 | 4 | 4 | 4 | 4 | 3 | 4 |
| morning-briefing | 4 | 2 | 4 | 4 | 3 | 4 | 2 | 4 |

The shape of the result is unambiguous: **first place on differentiation, last place overall**, and the loss is concentrated in three columns — reading depth, freshness, distribution. Every one of those is fixable without touching the edition engine.

---

## 3. Where it genuinely wins

Verified in code, not just claimed in the README:

- **Edition semantics exist nowhere else.** `buildEdition()` numbers editions, dates them by the reader's local day (`localIso`, so a 23:30 print is today's paper), keeps a bounded archive of 7 (`mergeArchive`), and *replaces* the same day's front page instead of stacking duplicates.
- **Cross-source clustering.** `cluster()` merges by canonical URL (tracking params stripped, `canonicalUrl`) then by headline token overlap with a light stemmer (`similarity`, Jaccard ≥ 0.6). A story carried by three mastheads prints once, credits all three, and keeps the fullest summary and earliest filing date. No competitor does this — they all render feeds as flat lists.
- **Reprint suppression.** Keys from the last earlier-day edition (link + normalised headline) are withheld, and the page says how many (`withheld`). This is the single most newspaper-like behaviour in the category and no rival has an analogue.
- **Standfirst diff.** `editionDiff()` produces *"7 new since No. 12 · 2 still running · 1 gone from your feeds"* — a comparison between printings, not an AI summary. Cheap, deterministic, and it is the feature most likely to make someone return.
- **Interests, not subscriptions.** Type `housing in Málaga`; the backend expands it to a query feed. This is a materially lower-friction onboarding than every rival's "add a feed URL" (they mitigate with discovery, but you still start from a publisher).
- **Model-free by default with a guarded opt-in.** Persona styling is the only model call, it is user-pressed, bounded to 12 stories, and a rewrite that invents a number, comes back empty or doubles the source length is discarded with the publisher's wording printed beneath (`dashboard/personas.py`). That is a stricter fidelity contract than any rival's summariser offers, and the edition still prints when the model is absent.
- **Security posture is above the field's median.** Literal-IP connection after DNS vetting, TLS verified against the original hostname, non-global addresses refused, no redirects, 12 s timeout, 2 MB cap, DTD/entity and UTF-16 XML rejected, no shell, no credential store. `hermes plugins validate` returns **safe**, and the isolation note is clean.

**Tests:** 41 Python + 19 Node (`node --test`) all pass on this machine; `node tests/desktop.mjs` registration/empty-state smoke passes; `hermes plugins doctor` passes. `hermes-newswire` is the only rival with a heavier suite (119 pytest + 55 UI checks), and it is the one competitor whose robustness clearly beats yours.

---

## 4. Where it loses

### 4.1 Reading depth — the biggest gap (2/5)
Daily Edition hands every headline to the system browser. `rss-reader` captures full articles into reader mode with a background queue (80 articles, two workers), renders sanitised HTML/Markdown/tables and YouTube embeds; `rss-lite` double-sanitises article HTML, ships a reader pane and in-app video; `hermes-rss` has "Load full article" and image handling. The README lists article extraction under *Known limitations*. Consequence: the paper is a **launcher**, and a reader who wants to actually read leaves on click one and may not come back.

### 4.2 State — no read/unread, no saved (2/5 personalisation component)
No `keydown` handler exists in `desktop/plugin.js` (grep count: 0), and there is no read, saved, tag or search state. Every rival has at least read/unread; `rss-lite` and `rss-reader` also have saved items, per-feed views, search and `j`/`k`/`/`/`r` shortcuts. Watchwords and mutes are good, but they are filters, not reading state.

### 4.3 Freshness and offline (2/5)
Feeds are fetched on open and on demand only — no polling, no conditional GET, no cache. `hermes-newswire` keeps the ticker alive from a SQLite cache with ETag/Last-Modified 304s and a 30 s–24 h refresh interval; `rss-lite` auto-refreshes at 5/15/30/60 min and backs off on failure; `rss-reader` has a persistent capture queue. A newspaper that is blank when the network is down is worse than a feed that is stale.

### 4.4 Source coverage and limits
- 12 interests, 20 fixed feeds, 20 printed stories (vs. unlimited subscriptions elsewhere).
- RSS/Atom only: no JSON Feed (newswire, rss-lite), no YouTube channels/playlists, no Reddit, no Substack (rss-reader, rss-lite).
- Discovery reads `<link rel="alternate">` then six conventional paths — the README itself concedes arstechnica.com fails.
- OPML **import only**; every rival with OPML also exports it, so there is no exit path.
- **Redirects are not followed at all.** Safer than rivals per-hop validation, but it silently fails on the large share of feeds behind a moved or short URL.

### 4.5 Agent surface — 0 tools, 0 hooks
`hermes plugins doctor`: *"0 tool(s), 0 hook(s)"*. Rivals integrate with the agent: `rss-reader` registers an `rss` toolset and twelve `/rss` slash commands (digest, health, mark-read, mute, find), `hermes-blogwatcher` ships `blogwatcher_list_sources` / `blogwatcher_list_articles`. This matters competitively for a specific reason: **it means the agent cannot print your paper**. That is exactly the capability `morning-briefing` monetises with a 6 AM cron job.

### 4.6 Distribution — worst in the set (1/5)
- Not in the catalog (1063 entries checked; zero `daily-edition`).
- Not a git repository — no history, no pinned SHA, no update path (`hermes plugins update` needs provenance).
- **No LICENSE file** — blocks catalog admission and reuse outright.
- No screenshots or hero image; every rival ships one, and the catalog is a browsing surface.
- `plugin.yaml` declares no `requires_hermes`, so an incompatible host fails at runtime rather than at install.
- Install is a documented manual sequence (copy dir, enable agent plugin, restart gateway, enable desktop half), against `hermes plugins install rss-lite --enable` + `hermes gateway restart`.

`hermes-newswire` is the cautionary precedent in both directions: it is equally unpolished on packaging ("catalog submission pending"), yet it wins because it ships a *surface you can see without opening a page* (the ticker) and a 119-test suite.

### 4.7 Smaller deductions
- Back issues store 6 headlines and open a summary page, not the composed front page the README implies.
- Partial fetch failure replaces previously loaded content rather than keeping the last good edition.
- No notification when a new edition is ready (status chip polls storage every 5 s, which is fine, but nothing pushes).
- Layout has three text sizes and one font stack; no density/spacing controls, no sidebar-less "read the paper" focus mode.

---

## 5. Head-to-head on the features that decide the category

| Capability | daily-edition | rss-reader | rss-lite | newswire | hermes-rss | morning-briefing |
|---|---|---|---|---|---|---|
| Dated edition / front page | **yes** | no | no | no | no | yes (printed) |
| Cross-outlet story clustering | **yes** | no | no | no | no | no |
| Reprint suppression across days | **yes** | no | no | read-state only | read-state only | no |
| "What changed" standfirst | **yes** | no | no | no | no | no |
| Back issues | 7 (summaries) | saved items | saved items | cache | saved items | printed pages |
| Reader view / full text | no | **yes** | **yes** | in-app read | **yes** | no |
| Read / saved state | no | **yes** | **yes** | unread | **yes** | n/a |
| Offline cache | no | yes | yes | **SQLite** | no | n/a |
| Auto-refresh | no | 1–1440 min | 5–60 min | 30 s–24 h | 1–1440 min | cron |
| Folder organisation | n/a | **yes** | **yes** | no | no | no |
| Search | no | **yes** | **yes** | **yes** | **yes** | no |
| OPML import / export | import only | both | both | import | both | no |
| YouTube / Reddit / Substack | no | **yes** | **yes** | no | no | no |
| Agent tools / slash commands | **none** | `rss` + 12 cmds | none | none | none | skill+cron |
| Presence when closed | status chip + ⌘K | ticker (opt) | no | **ticker strip** | no | printed page |
| AI feature | persona rewrite, guarded | summaries, grading, digests | summaries | none | summaries, grading | whole brief |
| Scheduled output | no | no | no | no | no | **6 AM cron** |
| Install | manual | catalog | `--enable` | manual + confirm | catalog | copy skill |
| In catalog | **no** | yes | yes | yes | yes | yes |
| License | **none** | MIT | MIT | MIT | MIT | MIT |
| Test volume | 60 tests | moderate | ~30+ | **119 + 55 UI** | ~1 suite | 0 (skill) |

---

## 6. Reading of the competition

- **`rss-reader` is the benchmark.** It wins on breadth (tools, commands, capture, folders, search, grading) and polish (screenshot-driven README, three-column identity). Copy its *integration* playbook, not its shape.
- **`rss-lite` is the benchmark for engineering discipline.** SQLite per profile, backoff, 5 MB/20 s caps, entity refusal, crash isolation, OPML both ways, `--enable` install. Its README reads like a disclosure document; yours already does too — match its feature floor.
- **`hermes-newswire` proves presence beats a page.** A 28–40 px ticker creates ambient awareness with zero clicks. If you build one thing from it, build *"the top headline is visible while you work"* — you already have the engine; a strip is a rendering problem, not a fetching one.
- **`morning-briefing` proves the ritual wedge.** Its product is not a page; it is a 6 AM cron job that prints a page and the onboarding interview that configures it. It is weak on robustness (skill-only, WeasyPrint + CUPS dependencies) and won't run on a phone, but it owns the *scheduled newspaper* position that Daily Edition's name promises and doesn't yet claim.
- **`hermes-rss` / `hermes-blogwatcher`** are the long tail: single-file readers with AI grading, and a CLI-backed inbox. Neither threatens on differentiation, but both are installed and reviewed, which Daily Edition is not.

---

## 7. Recommendation

**Do not become a sixth RSS reader.** On reading depth, state, folders, search, OPML export and source coverage you are 2–4 features behind three mature products, and catching up would erase the only thing that makes the plugin worth installing. Compete as *the edition*, and close only the gaps that block the edition from being usable.

### P0 — parity needed before anyone can adopt it (≈ 2–3 days)
1. **Read/saved state + in-app article view.** Sanitised capture into a reading pane; keep the paper as the front page and let a story open inside it. Without this the page is a directory of links.
2. **Persist the last good edition** in `ctx.storage` (headlines + snippets, as you already do for back issues) and render it when fetching fails or offline, with a visible "as of" stamp.
3. **Follow redirects safely** (max 3 hops, each hop through the existing DNS-pinning gate) and **export OPML**. Both are small and both remove silent failure and lock-in.
4. **Keyboard:** `j`/`k` between stories, `r` reprint, `/` search/filter. Two hours of work; it is the difference between a page and a product.

### P1 — turn the differentiator into a product (≈ 3–5 days)
5. **Ship the ritual:** a `daily-edition` skill + `hermes cron` recipe that prints at a chosen hour, plus a desktop notification and an optional "morning edition ready" chat message. This is the feature `morning-briefing` sells and it is the natural job of a *daily* paper. It also makes interests a set-and-forget subscription rather than a thing you remember to open.
6. **Give the agent a handle:** one tool (`print_edition`, returns lead + standfirst + sections) and one slash command (`/edition`, `/edition diff`). Costs ~100 lines, converts the plugin from page-only to agent-usable, and lets cron produce the daily print without a headless render.
7. **Fix distribution:** add `LICENSE` (MIT), `git init` + first commit, `requires_hermes` in `plugin.yaml`, a hero screenshot and two panel shots, then submit to the catalog. Today you are invisible in the only place 1,063 plugins are discovered.

### P2 — widen the moat (opportunistic)
8. A **headline ticker strip** reusing `edition.js` output (top 3 of the printed set, hover-pause) — competes with newswire on presence without competing on reader features.
9. Source types: **JSON Feed**, YouTube channel/playlist, Substack. Cheap once the adapter exists.
10. **Clustering quality:** add URL-slug similarity and entity match to the 0.6 headline-overlap rule; log which merges happened so a wrong merge is auditable. This is your moat — invest in it before breadth.
11. Raise caps (12 interests → 30; 20 stories → configurable) and add a focus/"read the paper" mode that hides all chrome.

### Score projection
P0 + P1 as scoped moves reading depth 2→4, freshness 2→4, integration 3→4, distribution 1→5, personalisation 3→4: weighted index **61 → ~83**, ahead of `rss-lite` (78) and just behind `rss-reader` (81) — while remaining the only plugin in the category nobody can substitute for on editions, clustering or reprints.

---

## 8. Honest caveats about this audit

- Competitor scores derive from pinned catalog READMEs and repo trees, not from installing and driving each plugin. Feature claims are as-good-as-their-documentation; `rss-reader`'s and `rss-lite`'s are unusually specific, `hermes-rss`'s less so.
- Daily Edition was exercised through its own test suites, `hermes plugins validate` and `hermes plugins doctor` — **not** end-to-end in a live Hermes Desktop session with a real gateway. Its README says the same, and that gap is part of the distribution problem.
- No usage, install or star data exists in the catalog, so "competitive" here means *feature and packaging position*, not measured adoption.

---

## 9. Status after v0.3.0 (2026-11-05)

Implemented and verified since this audit was written:

- **P0.1** in-app reading (`dashboard/reader.py` + reader pane): publisher pages reduced to typed text blocks; no publisher HTML reaches the renderer.
- **P0.2** last-good edition persisted (`lastEdition`); a failed refresh now shows the paper with an *as of* line instead of nothing, and the stored edition is the first paint.
- **P0.3** redirects followed up to three hops, each hop re-vetted; **OPML export** added (round-trips through the parser, refuses loopback/private URLs).
- **P0.4** keyboard: `j`/`k`, `Enter`, `s`, `r`, `/`, `u`, `Esc`; read/saved/search/unread views with bounded state.
- **P1.5/P1.6** `daily_edition` tool (print/diff/sources) and `/edition` command, composed by a Python port of the edition model held to the JS by a parity test; a `daily-edition` skill carries the tested cron recipe for the morning print.
- **P1.7** `LICENSE` (MIT), git repository with a first commit, `requires_hermes: ">=0.22.5"`, `provides_tools` declared, README rewritten, `validate` and `doctor` clean.

Verification actually run: 78 Python tests (including six parity tests against Node), 19 Node edition tests, the desktop render harness (empty state, composed paper, read/saved counts), `hermes plugins validate` → **passed/safe**, `hermes plugins doctor` → **1 tool, 0 hooks**, and one live end-to-end print against a real public feed (`hnrss.org/frontpage`, 3 stories composed, no source errors).

Still blocked, honestly:

- **Screenshots/hero images** need a live Hermes Desktop session; none were fabricated.
- **Catalog submission** needs a public repository URL (the local repo has no remote) and a maintainer account.
- **Electron end-to-end** behaviour (real keyboard events, reader scrolling, clipboard) is exercised only through the DOM-less harness, not a running Desktop app.

