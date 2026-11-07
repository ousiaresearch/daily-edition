# Corrections

Kept in the open, in the order they happened: the wrong thing quoted, the date, the cause, the fix,
and what remains after the fix.

## 2026-11-06 — personal identity in public commit metadata

**Wrong.** Every commit in this repository, and both release tags, carried an author and committer
identity that the exclusion list forbids: first the shell's ambient git identity (a personal name with
a `localhost` address), then a hand-typed company identity (`Ousia Research <dev@…>`) instead of the
organisation's publishing identity. The values are redacted here deliberately — repeating them would
publish the thing being removed.

**Cause.** The repository was created and committed from a terminal whose git identity was the
machine's, and the follow-up commits reused a second invented identity rather than the one every other
`ousiaresearch` repo uses. No file-content check can see this: the working tree, the licence, the
tests and the plugin contract all passed while the metadata carried the name.

**Fix.** All commits and both tags were rewritten
(`git filter-branch --env-filter`) to `Isildur <261687298+ousiaresearch@users.noreply.github.com>`,
force-pushed, and read back from the GitHub API — the repository's commit list now returns only that
identity for both author and committer. `user.name` and `user.email` are set repo-locally, so the next
commit cannot repeat it. The public timeline of this repository was reset to the first commit.

**Residue.** The organisation's activity feed, and any webhook or email notification generated before
the rewrite, may still show the old author on those events; they cannot be rewritten from here. Fork
count at the time of the rewrite: zero, so no downstream copy carries the old metadata.

**Rule going forward** (from the front-door policy): set the commit identity before the first commit,
not after the first push.
