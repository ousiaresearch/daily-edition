# Release checklist

A release is a tagged commit whose claims are backed by something that actually ran. This file lists
what is verified, how it was verified, and what is deliberately left to a human pass.

## Automated, runs on every push (`.github/workflows/ci.yml`)

| Gate | Command | Covers |
|---|---|---|
| Python suite | `python -m unittest discover -s tests -v` | backend, reader extraction, state, print pipeline, compose, tool/command registration, JS↔Python parity |
| Node suite | `node --test tests/edition.test.mjs` | edition model: clustering, reprints, sections, archive |
| Render harness | `node tests/desktop.mjs` | plugin registration, empty state, composed-paper render, unread/saved counts |
| Packaging | `python -m unittest tests.test_packaging` | manifest/plugin.yaml agreement, entry points, changelog version |
| Manifest, locally | `hermes plugins validate .` | plugin contract + security scan — needs a Hermes install, so CI skips it when the CLI is absent |

## Verified by hand, recorded here rather than asserted in a README

| Claim | How it was checked | Result |
|---|---|---|
| Fresh clone is self-contained | `git clone` to a temp dir, then all suites | 103 Python, 24 Node, harness, `validate` — pass |
| A composed edition prints to one page | live HN feed → PDF → rendered to an image and inspected | 1 page, fill 91%, no split headlines, columns level |
| Install from GitHub into an empty profile | clone → `hermes plugins adopt` → `enable` → `doctor` | recorded in the install notes below |
| Reader extraction keeps no markup | `tests/test_reader.py` | pass |

## Deliberately not proven

- **The Desktop half in a running Desktop app.** The harness invokes the components directly; it does
  not prove Electron accepts the page, that `ctx.storage` persists across restarts, or that the
  keyboard handling behaves with focus in the composer. One human pass is required before claiming
  this publicly: open the page, use `j`/`k`/`s`/`r`/`/`, open a story, export OPML, press Print.
- **Printing on a physical printer.** `lpstat -p` reports no destinations on the development machine,
  so the CUPS submission path is covered by tests with a mocked queue. The PDF and plain-text
  artifacts are real; the paper is not.
- **A second platform.** Everything was exercised on macOS with Chrome. Linux/Windows paths exist
  (printer discovery, font stacks, the Chrome candidate list) but are untested.

## Release process

1. Update `CHANGELOG.md`, bump `plugin.yaml`, bump `dashboard/manifest.json` (a test fails if they
   disagree or if the changelog has no entry for the manifest version).
2. Run the four gates locally; confirm CI is green on the release commit.
3. `git tag -s v<version> -m "Daily Edition <version>"` and push the tag.
4. Write the release notes from the changelog, and state the "deliberately not proven" section above
   verbatim. A release note that hides an untested surface is worse than a smaller release.
5. Post-release: install from the tag in a clean profile once (`git clone --branch v<version>`), so a
   broken tag is discovered before a user finds it.

## Rollback

Tags are immutable once published. To withdraw a release, publish a new patch version that reverts
the change, mark the old release in GitHub as a pre-release, and say why in the changelog. Never
force-push a tag a user may have installed.

## Install (verified path)

```bash
git clone https://github.com/ousiaresearch/daily-edition "$HERMES_HOME/plugins/daily-edition"
hermes plugins adopt daily-edition
hermes plugins enable daily-edition
hermes gateway restart
```

`hermes plugins install <local path>` does **not** work for a directory — it parses the path as a
GitHub repository. Clone into the profile's plugin directory and adopt it, or install the published
repository by URL.
