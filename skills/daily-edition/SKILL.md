---
name: daily-edition
description: "Set up a morning Daily Edition print with cron, and read the paper from chat."
version: 1.0.0
metadata:
  hermes:
    tags: [daily-edition, news, cron, briefing, rss]
---

# Daily Edition from chat and cron

The Daily Edition plugin composes a dated newspaper from the reader's saved interests and feeds.
The page is the main surface; this skill covers the two things you cannot do from the page —
printing the paper on a schedule, and answering questions about it in conversation.

## What you can rely on

- The `daily_edition` tool is deterministic and model-free. It fetches the reader's sources, merges
  cross-posted stories, ranks by consensus, withholds anything already printed on an earlier day,
  and returns the front page as text plus `number`, `dateLabel`, `storyCount`, `crossPosted`,
  `withheld`, `standfirst` and any per-source `errors`.
- `action: "sources"` lists what the paper draws on; `action: "diff"` returns only what changed
  since the last edition; `action: "print"` returns the whole front page.
- `/edition` prints, `/edition diff` gives the standfirst, `/edition sources` lists subscriptions.
- **The reader's interests and feeds live in the Desktop page's storage.** The page mirrors them to
  `$HERMES_HOME/daily-edition/state.json` whenever they change. If the tool reports no interests,
  the page has never been opened on that profile — do not invent interests, ask the user to open
  Daily Edition once (or pass `interests` explicitly for a one-off).
- No key, no model, and no background polling are involved. Each call fetches every source live,
  so a call takes a few seconds and reflects the feeds at that moment.

## Setting up the morning print

Ask before creating a scheduled job, and confirm the hour and weekday set. Then:

```bash
hermes cron create "0 7 * * 1-5" \
  "Print my Daily Edition: call the daily_edition tool with action=print, then give me the front page — lead first, then the sections, and say how many stories were withheld as already printed. If it returns errors for some sources, name them in one line." \
  --name "Daily Edition — weekday print" \
  --deliver origin \
  --skill daily-edition \
  --pin
```

- `--deliver origin` sends it to the chat the job was created from; use `--deliver local` to file it
  without a notification, or a platform name for another surface.
- `--pin` matters: an unpinned job drifts onto whatever the global default model is that morning.
- `--timezone` if the user's clock differs from the host's.
- Check it with `hermes cron runs <job>` after the first firing.

A weekday print at 07:00 and a Sunday `0 9 * * 0` "week in review" run are the two useful defaults.

## Reading it in conversation

- "What's in today's paper?" → `daily_edition` with `action=print`.
- "What's new since yesterday?" → `action=diff`.
- "What am I subscribed to?" → `action=sources`.
- A one-off interest ("what's happening with the port authority?") → pass
  `interests: ["the port authority"]` and do **not** save it; that override is per call only.
- Never summarise a story the tool did not return, and never present a headline as verified fact —
  the paper carries publisher titles and links, not confirmed reporting.

## Failure modes worth naming

| Symptom | Meaning |
|---|---|
| `Could not print the edition` with `no interests` | The page has never mirrored its state; ask the user to open it. |
| `errors: ["<source>: Server returned HTTP 429"]` | One publisher is rate-limiting; the rest of the paper still printed. |
| `withheld` equals `storyCount` on a reprint | Everything in the feeds already ran today or earlier; print tomorrow, or widen the interests. |
| Empty `state.json` after a reinstall | Interests live in Desktop storage, not the backend; re-add them on the page. |

Do not fix a broken source by inventing a replacement feed. Report it, or ask which source to add.
