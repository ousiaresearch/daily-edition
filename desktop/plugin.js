import { PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'
import { buildEdition, editionDiff, editionSummary, localIso, mergeArchive } from './edition.js'

const el = (type, props, ...children) => jsx(type, { ...props, children: children.length === 1 ? children[0] : children })
const muted = { color: 'var(--ui-text-secondary)' }
const rule = '1px solid var(--ui-stroke-secondary)'
const button = { border: rule, borderRadius: 5, padding: '6px 10px', cursor: 'pointer', background: 'transparent', color: 'inherit' }
const chipStyle = active => ({ ...button, fontSize: 12, ...(active ? {} : muted) })
const serif = { fontFamily: 'Georgia, serif' }
const scale = { compact: 0.9, normal: 1, large: 1.14 }
const MAX_SOURCES = 60
const MAX_INTERESTS = 30
const MAX_READ = 2000
const MAX_SAVED = 100
const ROUTE = '/daily-edition'

// Shown before the backend roster arrives; the backend is authoritative about what exists.
const PERSONA_FALLBACK = [
  { id: 'librosmarcus', name: 'LibrosMarcus' },
  { id: 'juno', name: 'Juno Glitch' },
  { id: 'quell', name: 'Inspector Ambrose Quell' },
  { id: 'hollis', name: 'Hollis, Crier of Mossgate' },
  { id: 'wire', name: 'The Wire' }
]

function StyledHeadline({ story, size, lead, onOpen }) {
  const entry = story.style
  const styled = entry && entry.ok ? entry.styled : ''
  const shown = styled || story.title
  return el('div', null,
    el('button', {
      type: 'button', onClick: () => onOpen(story), title: 'Read this story',
      style: {
        ...serif, textAlign: 'left', fontWeight: 600, padding: '4px 0', cursor: 'pointer',
        background: 'transparent', border: 0, color: 'inherit',
        fontSize: lead ? `clamp(${24 * size}px, 4vw, ${40 * size}px)` : 20 * size,
        lineHeight: lead ? 1.1 : 1.25
      }
    }, shown),
    styled ? el('div', { style: { ...muted, fontSize: 11, marginBottom: 2 } }, `Filed: “${story.title}”`) : null)
}

function SaveButton({ story, saved, onSave }) {
  return el('button', {
    type: 'button', onClick: () => onSave(story), 'aria-pressed': saved,
    title: saved ? 'Remove from saved' : 'Save this story',
    style: { ...button, border: 0, padding: '0 4px', fontSize: 11, ...muted }
  }, saved ? '★ saved' : '☆ save')
}

function Byline({ story, saved, onSave }) {
  // Who filed it. Falls back to the interest that surfaced it when a plain feed has no masthead.
  const label = (story.publishers && story.publishers.length ? story.publishers : story.sources || []).join(' · ')
  return el('div', { style: { ...muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.1em', display: 'flex', justifyContent: 'space-between', gap: 8 } },
    el('span', null, story.pinned ? '★ ' : '', label, story.publishers && story.publishers.length > 1 ? ' — cross-posted' : ''),
    onSave ? el(SaveButton, { story, saved, onSave }) : null)
}

function Masthead({ edition, loading, onRefresh, onStyle, styling, personaName, onPrint, printing }) {
  return el('header', {
    style: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', borderBottom: '2px solid var(--ui-stroke-secondary)', paddingBottom: 12, gap: 10 }
  },
    el('div', null,
      el('div', { style: { ...muted, textTransform: 'uppercase', letterSpacing: '.18em', fontSize: 11 } },
        'A newspaper of your own', edition ? ` · No. ${edition.number}` : ''),
      el('h1', { style: { ...serif, fontSize: 'clamp(36px, 6vw, 62px)', lineHeight: 1, margin: '10px 0 4px' } }, 'Daily Edition'),
      edition ? el('div', { style: { ...muted, fontSize: 13 } }, edition.dateLabel) : null),
    el('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
      personaName ? el('button', {
        type: 'button', onClick: onStyle, style: button, disabled: styling || loading
      }, styling ? 'Styling...' : `Style as ${personaName}`) : null,
      el('button', {
        type: 'button', onClick: onPrint, style: button, disabled: printing || loading || !(edition && edition.storyCount),
        title: 'Render this edition as a one-page sheet and send it to the printer'
      }, printing ? 'Printing on paper...' : 'Print the paper'),
      el('button', { type: 'button', onClick: onRefresh, style: button, disabled: loading }, loading ? 'Printing...' : 'Print new edition')))
}

function BackIssue({ summary, onBack, onOpen, ctx }) {
  return el('main', { style: { overflowY: 'auto', height: '100%', padding: '32px clamp(18px, 5vw, 70px)', maxWidth: 1100, margin: 'auto' } },
    el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' } },
      el('span', { style: { ...muted, ...serif, fontSize: 13 } }, `No. ${summary.number} · ${summary.dateLabel}`),
      el('button', { type: 'button', onClick: onBack, style: button }, 'Back to the front page')),
    el('h1', { style: { ...serif, fontSize: 'clamp(32px, 5vw, 52px)', lineHeight: 1.05, margin: '18px 0 6px' } },
      summary.leadTitle || 'An edition without a lead story'),
    summary.leadUrl ? el('button', {
      type: 'button', onClick: () => ctx.os.openExternal(summary.leadUrl),
      style: { ...muted, ...button, fontSize: 12 }
    }, 'Read the original ↗') : null,
    el('section', { 'aria-label': 'Headlines from this edition', style: { marginTop: 26, borderTop: rule, paddingTop: 14 } },
      ...(summary.headlines || []).slice(1).map((story, i) => el('article', { key: story.url + i, style: { borderTop: rule, padding: '10px 0' } },
        el('div', { style: { ...muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.1em' } }, (story.sources || []).join(' · ')),
        el('button', {
          type: 'button', onClick: () => (onOpen ? onOpen(story) : ctx.os.openExternal(story.url)),
          style: { ...serif, textAlign: 'left', fontSize: 17, lineHeight: 1.3, padding: '4px 0', cursor: 'pointer', background: 'transparent', border: 0, color: 'inherit' }
        }, story.title)))))
}

function Reader({ view, story, onBack, onExternal, saved, onSave }) {
  const article = view.data
  const blocks = (article && article.blocks) || []
  const minutes = article && article.words ? Math.max(1, Math.round(article.words / 220)) : 0
  const byline = (story.publishers && story.publishers.length ? story.publishers : story.sources || []).join(' · ')
  return el('main', { style: { overflowY: 'auto', height: '100%', padding: '28px clamp(18px, 5vw, 70px) 60px', maxWidth: 760, margin: 'auto' } },
    el('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' } },
      el('button', { type: 'button', onClick: onBack, style: { ...button, fontSize: 12 } }, '← Back to the paper'),
      el('div', { style: { display: 'flex', gap: 6 } },
        el(SaveButton, { story, saved, onSave }),
        el('button', { type: 'button', onClick: () => onExternal(story.url), style: { ...button, fontSize: 12 } }, 'Open original ↗'))),
    el('h1', { style: { ...serif, fontSize: 'clamp(26px, 4vw, 38px)', lineHeight: 1.15, margin: '18px 0 6px' } },
      (article && article.title) || story.title),
    el('div', { style: { ...muted, fontSize: 12, marginBottom: 18 } },
      [byline, story.date, minutes ? `${minutes} min read` : '', article && article.truncated ? 'abridged' : ''].filter(Boolean).join(' · ')),
    view.loading ? el('p', { role: 'status', style: muted }, 'Fetching the story…') : null,
    view.error ? el('div', { style: { borderTop: rule, paddingTop: 12 } },
      el('p', { role: 'alert', style: { ...muted, fontSize: 14 } }, `Could not read this page in the paper: ${view.error}`),
      el('p', { style: { fontSize: 13, ...muted } }, 'The publisher’s own page still works.'),
      el('button', { type: 'button', onClick: () => onExternal(story.url), style: button }, 'Open the original ↗')) : null,
    ...blocks.map((block, i) => {
      const style = { ...serif, fontSize: block.type === 'h2' ? 22 : block.type === 'h3' ? 18 : 17, lineHeight: 1.6, marginBottom: 14, maxWidth: '68ch' }
      if (block.type === 'h2' || block.type === 'h3') {
        return el('h2', { key: i, style: { ...style, fontWeight: 700, marginTop: 22 } }, block.text)
      }
      if (block.type === 'li') {
        return el('div', { key: i, style: { ...style, display: 'flex', gap: 8 } }, el('span', { style: muted }, '•'), el('span', null, block.text))
      }
      if (block.type === 'quote') {
        return el('blockquote', { key: i, style: { ...style, borderLeft: '2px solid var(--ui-stroke-secondary)', paddingLeft: 12, ...muted } }, block.text)
      }
      return el('p', { key: i, style }, block.text)
    }),
    blocks.length ? el('div', { style: { borderTop: rule, marginTop: 24, paddingTop: 12, display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' } },
      el('span', { style: { ...muted, fontSize: 12 } }, `Read here as text. Filed by ${byline}.`),
      el('button', { type: 'button', onClick: () => onExternal(story.url), style: { ...button, fontSize: 12 } }, 'Open original ↗')) : null)
}

function Preferences({ prefs, setPrefs, known, mutedUrls, toggleMute, watchInput, setWatchInput, addWatchwords }) {
  return el('details', { style: { border: rule, borderRadius: 6, padding: '8px 12px', marginBottom: 16 } },
    el('summary', { style: { cursor: 'pointer', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.14em', ...muted } },
      'Preferences · type, watchwords, muted sources'),
    el('div', { style: { display: 'flex', gap: 16, flexWrap: 'wrap', margin: '12px 0 4px', alignItems: 'center' } },
      el('span', { style: { fontSize: 12, ...muted } }, 'Text size'),
      ...['compact', 'normal', 'large'].map(size => el('button', {
        key: size, type: 'button', onClick: () => setPrefs({ ...prefs, textSize: size }),
        'aria-pressed': prefs.textSize === size, style: chipStyle(prefs.textSize === size)
      }, size))),
    el('form', { onSubmit: addWatchwords, style: { display: 'flex', gap: 8, margin: '12px 0 4px', flexWrap: 'wrap' } },
      el('input', {
        'aria-label': 'Watchwords, separated by commas', value: watchInput,
        placeholder: 'watchwords: fusion, transit, harbour',
        onChange: e => setWatchInput(e.target.value),
        style: { border: rule, padding: 6, borderRadius: 5, flex: 1, minWidth: 200, background: 'transparent', color: 'inherit', fontSize: 13 }
      }),
      el('button', { type: 'submit', style: { ...button, fontSize: 12 } }, 'Save watchwords')),
    (prefs.watchwords || []).length ? el('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 } },
      ...prefs.watchwords.map(word => el('button', {
        key: word, type: 'button', onClick: () => setPrefs({ ...prefs, watchwords: prefs.watchwords.filter(w => w !== word) }),
        title: 'Stop watching this word', style: { ...button, fontSize: 11 }
      }, '★ ' + word + ' ×'))) : null,
    known.length ? el('div', null,
      el('div', { style: { fontSize: 12, ...muted, margin: '10px 0 6px' } }, 'Muted sources are left out of the edition entirely'),
      el('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } },
        ...known.map(entry => el('button', {
          key: entry.url, type: 'button', onClick: () => toggleMute(entry.url),
          'aria-pressed': mutedUrls.includes(entry.url),
          title: mutedUrls.includes(entry.url) ? 'Include this source again' : 'Leave this source out',
          style: { ...button, fontSize: 12, ...(mutedUrls.includes(entry.url) ? muted : {}), textDecoration: mutedUrls.includes(entry.url) ? 'line-through' : 'none' }
        }, entry.name)))) : null)
}

export function Edition({ ctx }) {
  const [interests, setInterests] = useState(() => ctx.storage.get('interests', []) || [])
  const [feeds, setFeeds] = useState(() => ctx.storage.get('feeds', []) || [])
  const [archive, setArchive] = useState(() => ctx.storage.get('archive', []) || [])
  const [known, setKnown] = useState(() => ctx.storage.get('sources', []) || [])
  const [mutedUrls, setMutedUrls] = useState(() => ctx.storage.get('muted', []) || [])
  const [read, setRead] = useState(() => ctx.storage.get('read', []) || [])
  const [saved, setSaved] = useState(() => ctx.storage.get('saved', []) || [])
  const [prefs, setPrefsState] = useState(() => ({ textSize: 'normal', watchwords: [], ...(ctx.storage.get('prefs', {}) || {}) }))
  const [input, setInput] = useState('')
  const [interestInput, setInterestInput] = useState('')
  const [candidates, setCandidates] = useState([])
  const [opml, setOpml] = useState('')
  const [showOpml, setShowOpml] = useState(false)
  const [watchInput, setWatchInput] = useState('')
  const [edition, setEdition] = useState(() => ctx.storage.get('lastEdition', null))
  const [stale, setStale] = useState('')
  const [errors, setErrors] = useState([])
  const [loading, setLoading] = useState(false)
  const [finding, setFinding] = useState(false)
  const [revision, setRevision] = useState(0)
  const [issue, setIssue] = useState(null)
  const [story, setStory] = useState(null)
  const [article, setArticle] = useState(null)
  const [articleError, setArticleError] = useState('')
  const [articleLoading, setArticleLoading] = useState(false)
  const [view, setView] = useState('all')
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(-1)
  const [opmlExport, setOpmlExport] = useState('')
  const [notice, setNotice] = useState('')
  const [roster, setRoster] = useState(PERSONA_FALLBACK)
  const [styleMap, setStyleMap] = useState({})
  const [styleNote, setStyleNote] = useState('')
  const [standfirst, setStandfirst] = useState(() => (ctx.storage.get('lastEdition', {}) || {}).standfirst || '')
  const [styling, setStyling] = useState(false)
  const [printing, setPrinting] = useState(false)
  const size = scale[prefs.textSize] || 1

  const personaName = (roster.find(entry => entry.id === prefs.persona) || {}).name || ''
  const setPrefs = next => { ctx.storage.set('prefs', next); setPrefsState(next) }

  useEffect(() => {
    let live = true
    ctx.rest('/personas', { timeoutMs: 8000 })
      .then(result => { if (live && result && Array.isArray(result.personas) && result.personas.length) setRoster(result.personas) })
      .catch(() => {})
    return () => { live = false }
  }, [])

  useEffect(() => {
    let live = true
    // Interests are the normal path; a plain feed URL is the advanced one. Either contributes
    // sections, so the paper is built from whatever the reader actually cares about.
    const tasks = [
      ...interests.map(name => ({ key: 'interest:' + name, label: name, path: '/topic?q=' + encodeURIComponent(name) })),
      ...feeds.map(url => ({ key: url, label: '', path: '/feed?url=' + encodeURIComponent(url) }))
    ]
    if (!tasks.length) { setEdition(null); setStandfirst(''); setErrors([]); setKnown([]); setStale(''); return () => { live = false } }
    setLoading(true)
    Promise.all(tasks.map(async task => {
      try { return { ...task, data: await ctx.rest(task.path, { timeoutMs: 20000 }) } }
      catch (error) { return { ...task, data: { error: String(error) } } }
    })).then(results => {
      if (!live) return
      const sources = results
        .filter(({ data }) => !data.error)
        .map(({ key, label, data }) => ({ url: key, source: label || data.source || key, items: data.items || [] }))
      const names = sources.map(({ url, source }) => ({ url, name: source }))
      if (names.length) { ctx.storage.set('sources', names); setKnown(names) }
      // Muted outlets contribute nothing at all — no stories, no byline, no consensus credit.
      const mutedNames = names.filter(entry => mutedUrls.includes(entry.url)).map(entry => entry.name)
      // Compare against the most recent edition from an EARLIER day, so: yesterday's repeats are
      // withheld, and re-printing today simply replaces today's front page instead of yielding to it.
      const stored = ctx.storage.get('archive', []) || []
      const iso = localIso(new Date())
      const previous = stored.find(entry => entry && entry.isoDate !== iso) || null
      const composed = buildEdition({ sources, previous, muted: mutedNames, watchwords: prefs.watchwords || [] })
      const remembered = ctx.storage.get('lastEdition', null)
      const diff = editionDiff(composed, previous)
      if (!sources.length && remembered && remembered.stories && remembered.stories.length) {
        // A dated paper from this morning beats a blank page; say how old it is.
        setEdition(remembered)
        setStandfirst(remembered.standfirst || '')
        setStale(remembered.dateLabel || remembered.isoDate || 'earlier')
      } else {
        setEdition(composed)
        setStandfirst(diff.line)
        setStale('')
        if (composed.storyCount) {
          // Keep the last good printing so a failed refresh still has today's paper on the desk.
          ctx.storage.set('lastEdition', {
            number: composed.number, isoDate: composed.isoDate, dateLabel: composed.dateLabel,
            builtAt: composed.builtAt, stories: composed.stories, lead: composed.lead,
            sections: composed.sections, storyCount: composed.storyCount,
            crossPosted: composed.crossPosted, sourceCount: composed.sourceCount,
            mutedCount: composed.mutedCount, pinnedCount: composed.pinnedCount,
            withheld: composed.withheld, omitted: composed.omitted, standfirst: diff.line
          })
        }
      }
      setStyleMap({})  // a new printing starts in the publisher's own words
      setStyleNote('')
      setErrors(results.filter(({ data }) => data.error).map(({ key, label, data }) => `${label || key}: ${data.error}`))
      const next = mergeArchive(stored, editionSummary(composed), 7)
      ctx.storage.set('archive', next)
      setArchive(next)
      setLoading(false)
    })
    return () => { live = false }
  }, [interests, feeds, revision, mutedUrls, prefs.watchwords])

  // The agent side composes from the same settings, so mirror them where it can read them.
  useEffect(() => {
    ctx.rest('/state', {
      method: 'POST', timeoutMs: 8000,
      body: { interests, feeds, muted: mutedUrls, watchwords: prefs.watchwords || [], persona: prefs.persona || '', archive }
    }).catch(() => {})
  }, [interests, feeds, mutedUrls, prefs.watchwords, prefs.persona, archive])

  const save = next => { ctx.storage.set('feeds', next); setFeeds(next) }
  const saveInterests = next => { ctx.storage.set('interests', next); setInterests(next) }
  const addInterest = phrase => {
    const name = String(phrase || '').trim().replace(/\s+/g, ' ')
    if (!name || name.length > 120) return
    if (interests.some(existing => existing.toLowerCase() === name.toLowerCase())) return
    if (interests.length >= MAX_INTERESTS) { setErrors([`Up to ${MAX_INTERESTS} interests.`]); return }
    saveInterests([...interests, name])
  }
  const submitInterest = event => {
    event.preventDefault()
    addInterest(interestInput)
    setInterestInput('')
  }
  const validUrl = raw => {
    try {
      const parsed = new URL(raw)
      if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash) return false
      return true
    } catch { return false }
  }
  const addFeed = url => {
    if (!validUrl(url)) { setErrors(['Enter an HTTP(S) URL without credentials or a fragment.']); return false }
    if (feeds.includes(url)) return true
    if (feeds.length >= MAX_SOURCES) { setErrors([`Up to ${MAX_SOURCES} sources.`]); return false }
    save([...feeds, url])
    return true
  }

  // A homepage is as good as a feed URL: ask the backend what it advertises.
  const find = async event => {
    event.preventDefault()
    const raw = input.trim()
    if (!validUrl(raw)) { setErrors(['Enter an HTTP(S) website or feed URL without credentials or a fragment.']); return }
    setFinding(true); setErrors([]); setCandidates([])
    try {
      const found = await ctx.rest('/discover?url=' + encodeURIComponent(raw), { timeoutMs: 20000 })
      if (found.error) { setErrors([`${raw}: ${found.error}`]); return }
      const list = (found.feeds || []).filter(entry => !feeds.includes(entry.url))
      if (!list.length) {
        setErrors(found.kind === 'page' ? [`No feed found at ${raw}.`] : [`${raw} is already a source.`])
        return
      }
      if (list.length === 1) { addFeed(list[0].url); setInput('') } else setCandidates(list)
    } catch (error) {
      setErrors([String(error)])
    } finally { setFinding(false) }
  }

  const importOpml = async event => {
    event.preventDefault()
    if (!opml.trim()) return
    try {
      const parsed = await ctx.rest('/opml', { method: 'POST', body: { text: opml }, timeoutMs: 20000 })
      if (parsed.error) { setErrors([parsed.error]); return }
      const incoming = (parsed.feeds || []).map(entry => entry.url).filter(url => !feeds.includes(url))
      const merged = [...feeds, ...incoming].slice(0, MAX_SOURCES)
      save(merged)
      setErrors(incoming.length ? [] : ['Every subscription in that file was already added.'])
      setOpml(''); setShowOpml(false)
    } catch (error) { setErrors([String(error)]) }
  }

  // Leaving must be as easy as arriving: hand the sources back as OPML.
  const exportOpml = async () => {
    setNotice('')
    try {
      const result = await ctx.rest('/opml/export', { method: 'POST', body: { feeds, interests }, timeoutMs: 15000 })
      if (result.error) { setErrors([result.error]); return }
      setOpmlExport(result.text)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(result.text)
        setNotice(`Copied ${feeds.length + interests.length} subscriptions as OPML.`)
      } else {
        setNotice('Select the OPML below and copy it.')
      }
    } catch (error) { setErrors([String(error)]) }
  }

  const toggleMute = url => {
    const next = mutedUrls.includes(url) ? mutedUrls.filter(entry => entry !== url) : [...mutedUrls, url]
    ctx.storage.set('muted', next)
    setMutedUrls(next)
  }
  const addWatchwords = event => {
    event.preventDefault()
    const words = watchInput.split(',').map(word => word.trim().toLowerCase()).filter(Boolean)
    if (!words.length) return
    setPrefs({ ...prefs, watchwords: [...new Set([...(prefs.watchwords || []), ...words])].slice(0, 24) })
    setWatchInput('')
  }

  const markRead = url => {
    if (read.includes(url)) return
    const next = [...read, url].slice(-MAX_READ)
    ctx.storage.set('read', next)
    setRead(next)
  }
  const isSaved = url => saved.some(entry => entry.url === url)
  const toggleSaved = item => {
    const exists = isSaved(item.url)
    const next = exists
      ? saved.filter(entry => entry.url !== item.url)
      : [...saved, {
        url: item.url, title: item.title, snippet: String(item.snippet || '').slice(0, 400),
        sources: item.sources || [], publishers: item.publishers || []
      }].slice(-MAX_SAVED)
    ctx.storage.set('saved', next)
    setSaved(next)
    setNotice(exists ? 'Removed from saved.' : 'Saved for later.')
  }

  // Reading happens in the paper: the publisher's page is extracted to plain text blocks, and the
  // original link is always one click away.
  const openStory = item => {
    setStory(item); setArticle(null); setArticleError(''); setArticleLoading(true); setCursor(-1)
    markRead(item.url)
    ctx.rest('/article?url=' + encodeURIComponent(item.url), { timeoutMs: 20000 })
      .then(result => { if (result.error) setArticleError(result.error); else setArticle(result) })
      .catch(error => setArticleError(String(error)))
      .finally(() => setArticleLoading(false))
  }
  const closeStory = () => { setStory(null); setArticle(null); setArticleError('') }

  // Persona styling is opt-in and never blocks the paper: any failure leaves the publisher's
  // wording on the page and says so.
  const styleEdition = async () => {
    if (!edition || !edition.storyCount || !prefs.persona) return
    setStyling(true); setStyleNote('')
    const batch = edition.stories.slice(0, 12)
    try {
      const result = await ctx.rest('/compose', {
        method: 'POST', timeoutMs: 60000,
        body: { persona: prefs.persona, stories: batch.map(s => ({ title: s.title, snippet: s.snippet })), limit: batch.length }
      })
      if (result.error) { setStyleNote(result.error); return }
      const next = {}
      ;(result.items || []).forEach((item, index) => {
        const story_ = batch[index]
        if (!story_) return
        if (item.ok) next[story_.url] = item
      })
      setStyleMap(next)
      const styled = Object.keys(next).length
      const kept = (result.items || []).length - styled
      setStyleNote(`${styled} headline${styled === 1 ? '' : 's'} in the voice of ${personaName}`
        + (kept ? `; ${kept} left as filed` : '')
        + `. Written by ${result.model} from the publisher's text — original wording printed beneath each.`)
    } catch (error) {
      setStyleNote(String(error))
    } finally { setStyling(false) }
  }

  // Paper, not just pixels: the same edition rendered to one sheet and handed to CUPS.
  const printPaper = async () => {
    if (!edition || !edition.storyCount) return
    setPrinting(true); setNotice(''); setErrors([])
    try {
      const result = await ctx.rest('/print', { method: 'POST', timeoutMs: 150000, body: { max_pages: 1 } })
      if (result.error) { setErrors([`Printing failed: ${result.error}`]); return }
      setNotice(`Sent ${result.stories} stories to ${result.printer || 'the default printer'} — job ${result.job} (${result.pages} page${result.pages === 1 ? '' : 's'}).`)
    } catch (error) { setErrors([String(error)]) } finally { setPrinting(false) }
  }

  const stories = (edition && edition.stories) || []
  const unread = stories.filter(item => !read.includes(item.url))
  const needle = query.trim().toLowerCase()
  const matches = item => !needle
    || String(item.title || '').toLowerCase().includes(needle)
    || String(item.snippet || '').toLowerCase().includes(needle)
    || (item.publishers || item.sources || []).join(' ').toLowerCase().includes(needle)
  const visible = (view === 'unread' ? unread : stories).filter(matches)
  const listed = view === 'saved' ? saved.filter(matches) : visible
  const filtering = view !== 'all' || Boolean(needle)

  // Keyboard first: j/k move, enter reads, s saves, r reprints, / searches, u toggles unread.
  useEffect(() => {
    const onKey = event => {
      const tag = (event.target && event.target.tagName) || ''
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        if (event.key === 'Escape' && event.target.blur) event.target.blur()
        return
      }
      if (event.key === 'Escape') {
        if (story) { closeStory(); return }
        if (issue != null) { setIssue(null); return }
        if (query) setQuery('')
        return
      }
      if (event.key === '/') {
        const box = document.getElementById('de-search')
        if (box) { event.preventDefault(); box.focus() }
        return
      }
      if (edition == null || loading) return
      if (event.key === 'j' || event.key === 'k') {
        event.preventDefault()
        setCursor(current => {
          if (!listed.length) return -1
          const next = event.key === 'j' ? current + 1 : current - 1
          return Math.max(0, Math.min(next, listed.length - 1))
        })
      }
      if (event.key === 'Enter' && listed[cursor]) { event.preventDefault(); openStory(listed[cursor]) }
      if (event.key === 's' && listed[cursor]) { event.preventDefault(); toggleSaved(listed[cursor]) }
      if (event.key === 'r' && !loading) { event.preventDefault(); setRevision(x => x + 1) }
      if (event.key === 'u') { event.preventDefault(); setView(view === 'unread' ? 'all' : 'unread') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [listed, cursor, story, issue, loading, query, view, read, saved])

  if (story) {
    return jsx(Reader, {
      view: { data: article, error: articleError, loading: articleLoading },
      story, saved: isSaved(story.url),
      onBack: closeStory, onExternal: url => ctx.os.openExternal(url), onSave: toggleSaved
    })
  }

  if (issue != null) {
    const summary = archive.find(entry => entry.number === issue)
    if (summary) return jsx(BackIssue, { summary, onBack: () => setIssue(null), onOpen: openStory, ctx })
  }

  const lead = edition && !filtering ? edition.lead : null
  const staged = candidates.length > 0
  return el('main', { style: { overflowY: 'auto', height: '100%', padding: '32px clamp(18px, 5vw, 70px)', maxWidth: 1100, margin: 'auto' } },
    jsx(Masthead, {
      edition, loading, onRefresh: () => setRevision(x => x + 1),
      onStyle: styleEdition, styling, personaName: edition && edition.storyCount ? personaName : '',
      onPrint: printPaper, printing
    }),
    el('p', { style: { ...muted, fontSize: 13, margin: '10px 0 0' } },
      interests.length
        ? `Today’s edition is drawn from ${interests.length} ${interests.length === 1 ? 'interest' : 'interests'}. Each printing is a dated edition you keep.`
        : 'Tell the paper what you care about — a subject, a place, a company — and it will compile that into a dated edition.'),
    stale ? el('p', { role: 'status', style: { fontSize: 12, ...muted, borderLeft: '2px solid var(--ui-stroke-secondary)', paddingLeft: 8, margin: '10px 0 0' } },
      `Showing the edition as of ${stale} — your sources could not be reached just now.`) : null,
    el('form', { onSubmit: submitInterest, style: { display: 'flex', gap: 8, margin: '18px 0 10px', flexWrap: 'wrap' } },
      el('input', {
        'aria-label': 'Add an interest', placeholder: 'e.g. fusion energy, housing in Málaga, the port authority',
        value: interestInput, onChange: e => setInterestInput(e.target.value),
        style: { border: rule, padding: 8, borderRadius: 5, minWidth: 220, flex: 1, background: 'transparent', color: 'inherit' }
      }),
      el('button', { type: 'submit', style: button }, 'Add interest')),
    el('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 } },
      ...interests.map(name => el('button', {
        key: name, type: 'button', onClick: () => saveInterests(interests.filter(entry => entry !== name)),
        title: 'Stop following this interest', 'aria-label': `Stop following ${name}`,
        style: { ...button, fontSize: 12 }
      }, name + ' ×'))),
    !interests.length && !feeds.length ? el('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 } },
      el('span', { style: { fontSize: 12, ...muted } }, 'Start from:'),
      ...['local government', 'AI policy', 'climate', 'markets', 'my city'].map(name => el('button', {
        key: name, type: 'button', onClick: () => addInterest(name),
        style: { ...button, ...muted, fontSize: 12 }
      }, name))) : null,
    el('details', { style: { border: rule, borderRadius: 6, padding: '8px 12px', marginBottom: 14 } },
      el('summary', { style: { cursor: 'pointer', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.14em', ...muted } },
        'Advanced · add a specific site, import or export OPML'),
      el('form', { onSubmit: find, style: { display: 'flex', gap: 8, margin: '12px 0 10px', flexWrap: 'wrap' } },
        el('input', {
          'aria-label': 'Website or feed URL', placeholder: 'https://example.com — or its feed URL', value: input,
          onChange: e => { setInput(e.target.value); setCandidates([]) },
          style: { border: rule, padding: 8, borderRadius: 5, minWidth: 220, flex: 1, background: 'transparent', color: 'inherit' }
        }),
        el('button', { type: 'submit', style: button, disabled: finding }, finding ? 'Looking...' : 'Find feed'),
        el('button', {
          type: 'button', onClick: () => setShowOpml(v => !v), 'aria-expanded': showOpml,
          style: { ...button, ...muted, fontSize: 12 }
        }, 'Import OPML'),
        el('button', {
          type: 'button', onClick: exportOpml, disabled: !feeds.length && !interests.length,
          style: { ...button, ...muted, fontSize: 12 }
        }, 'Export OPML')),
      showOpml ? el('form', { onSubmit: importOpml, style: { marginBottom: 12 } },
        el('textarea', {
          'aria-label': 'OPML subscription list', value: opml, onChange: e => setOpml(e.target.value),
          placeholder: 'Paste an exported OPML subscription list', rows: 4,
          style: { width: '100%', border: rule, borderRadius: 5, padding: 8, background: 'transparent', color: 'inherit', fontFamily: 'monospace', fontSize: 12 }
        }),
        el('button', { type: 'submit', style: { ...button, marginTop: 6 } }, 'Add every subscription')) : null,
      opmlExport ? el('textarea', {
        readOnly: true, 'aria-label': 'Exported OPML', value: opmlExport, rows: 4,
        style: { width: '100%', border: rule, borderRadius: 5, padding: 8, marginBottom: 10, background: 'transparent', color: 'inherit', fontFamily: 'monospace', fontSize: 11 }
      }) : null,
      staged ? el('div', { style: { borderTop: rule, paddingTop: 8, marginBottom: 8 } },
        el('div', { style: { fontSize: 12, ...muted, marginBottom: 6 } }, 'This page offers more than one feed. Add which?'),
        ...candidates.map(entry => el('button', {
          key: entry.url, type: 'button', style: { ...button, display: 'block', width: '100%', textAlign: 'left', marginBottom: 4, fontSize: 12 },
          onClick: () => { addFeed(entry.url); setCandidates(candidates.filter(c => c.url !== entry.url)) }
        }, entry.title ? `${entry.title} — ${entry.url}` : entry.url))) : null,
      feeds.length ? el('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
        ...feeds.map(url => el('button', {
          key: url, type: 'button', onClick: () => save(feeds.filter(f => f !== url)),
          title: 'Remove source', 'aria-label': `Remove ${url}`,
          style: { ...button, ...muted, fontSize: 12 }
        }, (known.find(entry => entry.url === url) || {}).name || url, ' ×'))) : null),
    jsx(Preferences, { prefs, setPrefs, known, mutedUrls, toggleMute, watchInput, setWatchInput, addWatchwords }),
    el('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 } },
      el('span', { style: { fontSize: 12, ...muted } }, 'Editorial voice'),
      el('button', {
        type: 'button', onClick: () => setPrefs({ ...prefs, persona: '' }),
        'aria-pressed': !prefs.persona,
        style: chipStyle(!prefs.persona)
      }, 'House style'),
      ...roster.map(entry => el('button', {
        key: entry.id, type: 'button', onClick: () => setPrefs({ ...prefs, persona: entry.id }),
        'aria-pressed': prefs.persona === entry.id, title: entry.strapline || '',
        style: chipStyle(prefs.persona === entry.id)
      }, entry.name))),
    styleNote ? el('p', { role: 'status', style: { ...muted, fontSize: 12, borderLeft: '2px solid var(--ui-stroke-secondary)', paddingLeft: 8, margin: '0 0 14px' } }, styleNote) : null,
    notice ? el('p', { role: 'status', style: { ...muted, fontSize: 12, margin: '0 0 10px' } }, notice) : null,
    ...errors.map((error, i) => el('p', { key: i, role: 'alert', style: { ...muted, overflowWrap: 'anywhere', fontSize: 13 } }, error)),
    !interests.length && !feeds.length ? el('p', { style: muted }, 'Add an interest above to make your first edition.') : null,
    (interests.length || feeds.length) && !loading && edition && !edition.storyCount && !errors.length
      ? el('p', { style: muted }, edition.withheld
        ? `Everything in these feeds already ran in an earlier edition. ${edition.withheld} ${edition.withheld === 1 ? 'story' : 'stories'} withheld.`
        : edition.mutedCount ? 'Everything you follow is muted. Unmute one in Preferences.' : 'No stories found for these interests today.')
      : null,
    edition ? el('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', margin: '6px 0 10px', borderTop: rule, paddingTop: 12 } },
      ...['all', 'unread', 'saved'].map(name => el('button', {
        key: name, type: 'button', onClick: () => { setView(name); setCursor(-1) },
        'aria-pressed': view === name, style: chipStyle(view === name)
      }, name === 'all' ? `All (${stories.length})` : name === 'unread' ? `Unread (${unread.length})` : `Saved (${saved.length})`)),
      el('input', {
        id: 'de-search', 'aria-label': 'Search this edition', value: query,
        placeholder: 'search headlines (/ to focus)',
        onChange: e => { setQuery(e.target.value); setCursor(-1) },
        style: { border: rule, padding: '4px 8px', borderRadius: 5, flex: 1, minWidth: 160, background: 'transparent', color: 'inherit', fontSize: 12 }
      }),
      el('span', { style: { fontSize: 11, ...muted } }, 'j/k move · enter read · s save · r reprint')) : null,
    standfirst && !filtering ? el('p', { style: { ...serif, fontSize: 13, fontStyle: 'italic', ...muted, margin: '0 0 6px' } }, standfirst) : null,
    edition && edition.storyCount && !filtering ? el('section', { 'aria-label': 'This edition', style: { marginTop: 8 } },
      el('p', { style: { ...muted, fontSize: 12, margin: '0 0 14px' } },
        `${edition.storyCount} ${edition.storyCount === 1 ? 'story' : 'stories'} from ${edition.sourceCount - edition.mutedCount} ${edition.sourceCount - edition.mutedCount === 1 ? 'source' : 'sources'}`
        + (edition.crossPosted ? ` · ${edition.crossPosted} cross-posted` : '')
        + (edition.pinnedCount ? ` · ${edition.pinnedCount} on your watchwords` : '')
        + (edition.mutedCount ? ` · ${edition.mutedCount} muted` : '')
        + (edition.withheld ? ` · ${edition.withheld} withheld as previously printed` : '')
        + (edition.omitted ? ` · ${edition.omitted} held over` : '')),
      lead ? el('article', { style: { borderTop: rule, paddingTop: 16, marginBottom: 22 } },
        jsx(Byline, { story: lead, saved: isSaved(lead.url), onSave: toggleSaved }),
        jsx(StyledHeadline, { story: { ...lead, style: styleMap[lead.url] }, size, lead: true, onOpen: openStory }),
        lead.snippet ? el('p', { style: { ...muted, fontSize: 15 * size, lineHeight: 1.55, margin: '8px 0 0', maxWidth: '62ch' } }, lead.snippet) : null,
        (lead.also || []).length > 1 ? el('p', { style: { ...muted, fontSize: 11 } }, 'Also reported by ' + lead.also.slice(1).map(entry => entry.source).join(', ')) : null)
        : null,
      ...edition.sections.map(section => el('section', { key: section.source, 'aria-label': section.source, style: { borderTop: rule, paddingTop: 12, marginBottom: 18 } },
        el('h2', { style: { fontSize: 12, textTransform: 'uppercase', letterSpacing: '.18em', margin: '0 0 6px', fontWeight: 700 } }, section.source),
        ...section.stories.map((item, i) => el('article', { key: item.url + i, style: { padding: '10px 0', borderTop: i ? rule : 'none' } },
          jsx(Byline, { story: item, saved: isSaved(item.url), onSave: toggleSaved }),
          jsx(StyledHeadline, { story: { ...item, style: styleMap[item.url] }, size, onOpen: openStory }),
          item.snippet ? el('p', { style: { ...muted, fontSize: 13 * size, lineHeight: 1.5, margin: '4px 0 0', maxWidth: '70ch' } }, item.snippet) : null)))))
      : null,
    edition && filtering ? el('section', { 'aria-label': 'Filtered stories', style: { marginTop: 8 } },
      el('p', { style: { ...muted, fontSize: 12, margin: '0 0 10px' } },
        view === 'saved' ? `${listed.length} saved ${listed.length === 1 ? 'story' : 'stories'}` : `${listed.length} matching ${listed.length === 1 ? 'story' : 'stories'}`),
      listed.length ? el('div', null, ...listed.map((item, i) => el('article', {
        key: item.url + i, style: { borderTop: rule, padding: '10px 0', background: i === cursor ? 'color-mix(in srgb, var(--ui-text-secondary) 8%, transparent)' : 'transparent' }
      },
        jsx(Byline, { story: item, saved: isSaved(item.url), onSave: toggleSaved }),
        jsx(StyledHeadline, { story: { ...item, style: styleMap[item.url] }, size, onOpen: openStory }),
        item.snippet ? el('p', { style: { ...muted, fontSize: 13 * size, lineHeight: 1.5, margin: '4px 0 0', maxWidth: '70ch' } }, item.snippet) : null)))
        : el('p', { style: muted }, view === 'saved' ? 'Nothing saved yet. Press s on a headline, or ☆ save.' : 'Nothing matches that search.'),
      view === 'saved' && listed.length ? el('p', { style: { ...muted, fontSize: 11, marginTop: 8 } }, 'Saved stories keep their headline and summary; open one to read it again.') : null) : null,
    archive.length > 1 ? el('nav', { 'aria-label': 'Back issues', style: { borderTop: rule, marginTop: 30, paddingTop: 14 } },
      el('h2', { style: { fontSize: 11, textTransform: 'uppercase', letterSpacing: '.18em', margin: '0 0 8px', ...muted } }, 'Back issues'),
      el('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
        ...archive.filter(entry => !edition || entry.number !== edition.number).map(entry => el('button', {
          key: entry.number, type: 'button', onClick: () => setIssue(entry.number),
          style: { ...button, fontSize: 12 }
        }, `No. ${entry.number} · ${entry.isoDate}`)))) : null)
}

// The status-bar chip keeps the paper present without opening it: latest edition, its story count,
// and a click that goes there. Reads plugin storage on a slow poll so it follows whatever the page
// last printed.
function EditionChip({ ctx }) {
  const read = () => {
    const archive = ctx.storage.get('archive', []) || []
    const latest = archive[0]
    if (!latest) return ''
    return `No. ${latest.number} · ${latest.storyCount} ${latest.storyCount === 1 ? 'story' : 'stories'}`
  }
  const [label, setLabel] = useState(read)
  useEffect(() => {
    const timer = setInterval(() => setLabel(read()), 5000)
    setLabel(read())
    return () => clearInterval(timer)
  }, [])
  if (!label) return null
  return el('button', {
    type: 'button', title: 'Open today\u2019s Daily Edition',
    onClick: () => { window.location.hash = '#/daily-edition' },
    style: { ...button, fontSize: 11, padding: '2px 8px', border: 0, ...muted }
  }, '\u25A4 ' + label)
}

export default {
  id: 'daily-edition', name: 'Daily Edition', defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(Edition, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROUTE, label: 'Daily Edition', codicon: 'book' } },
      {
        id: 'chip', area: 'statusBar.right',
        render: () => jsx(EditionChip, { ctx })
      },
      {
        // Reachable from ⌘K without hunting the sidebar; the note is the live state it acts on.
        id: 'open', area: PALETTE_AREA,
        data: {
          id: 'daily-edition:open',
          label: 'Daily Edition: open the paper',
          keywords: ['news', 'paper', 'edition', 'interests', 'headlines'],
          detail: () => {
            const latest = (ctx.storage.get('archive', []) || [])[0]
            return latest ? `No. ${latest.number} · ${latest.storyCount} stories` : 'no edition yet'
          },
          run: () => { window.location.hash = '#/daily-edition' }
        }
      }
    ])
  }
}
