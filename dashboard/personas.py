"""Editorial personas for Daily Edition.

A persona rewrites *headlines* in a voice. It never adds facts: the publisher's own headline and
snippet are the only material, the original headline is always printed underneath, and a rewrite
that invents a number or drifts too far from the source length is rejected and replaced by the
publisher's wording. The model is injected, so this module is fully testable offline.
"""

import re

PERSONAS = {
    'librosmarcus': {
        'name': 'LibrosMarcus',
        'strapline': 'Plain words, carefully kept.',
        'voice': ('Measured and bookish. Short declarative sentences, no exclamation marks, no hype. '
                  'Prefers the concrete noun to the abstract one.'),
    },
    'juno': {
        'name': 'Juno Glitch',
        'strapline': 'All signal, no sponsorship.',
        'voice': ('Wry and technical, faintly cynical about institutions and markets. Dry, never cruel, '
                  'never cute. Comfortable with a comma and a raised eyebrow.'),
    },
    'quell': {
        'name': 'Inspector Ambrose Quell',
        'strapline': 'Who benefits, and who signed for it.',
        'voice': ('Sceptical investigator. Leads with the claim under question and who is making it. '
                  'Cautious verbs, no verdict the source does not support.'),
    },
    'hollis': {
        'name': 'Hollis, Crier of Mossgate',
        'strapline': 'Hear it once, hear it true.',
        'voice': ('Declamatory town-crier register, period flavour, but every fact from the source and '
                  'nothing invented. No archaism that obscures meaning.'),
    },
    'wire': {
        'name': 'The Wire',
        'strapline': 'Filed straight.',
        'voice': 'Neutral wire-service style. Subject, verb, object. No adjectives that editorialise.',
    },
}

MAX_HEADLINE = 200
LENGTH_RATIO = 3.0

SYSTEM_RULES = (
    'You are the headline editor of a personal newspaper. Rewrite ONE headline in the given voice.\n'
    'Hard rules:\n'
    '- Use only the facts in the supplied headline and summary.\n'
    '- Do not add names, places, numbers or causes that are not in the supplied text. Never introduce a number.\n'
    '- Do not state an opinion as fact; voice may colour the phrasing, not the substance.\n'
    '- One line, no quotes around it, no "Headline:" prefix, no trailing full stop.\n'
    '- Keep it close in length to the original (never more than about twice as long).\n'
    '- Reply with the headline only.'
)


def _persona(persona_id):
    persona = PERSONAS.get(str(persona_id or '').strip().lower())
    if persona is None:
        raise ValueError('Unknown persona: %s' % persona_id)
    return persona


def build_prompt(persona_id, story):
    persona = _persona(persona_id)
    title = str(story.get('title') or '').strip()
    snippet = str(story.get('snippet') or '').strip()
    system = (
        SYSTEM_RULES
        + '\nVoice — %s (%s): %s' % (persona['name'], persona['strapline'], persona['voice'])
    )
    user = (
        'Publisher headline: %s\nPublisher summary: %s\n\nRewrite the headline in this voice.'
        % (title, snippet or '(none supplied)')
    )
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


_PREFIX = re.compile(r'^\s*(headline|title|rewrite)\s*[:\-—]\s*', re.I)
_WRAP = '"\'“”‘’`'


def sanitize_headline(text):
    line = ' '.join(str(text or '').split())
    line = _PREFIX.sub('', line)
    line = line.strip(_WRAP).strip()
    line = line.lstrip('-—–: ').strip()
    line = line.rstrip('.')
    return ' '.join(line.split())


def _numbers(text):
    return set(re.findall(r'\d+(?:[.,]\d+)?', str(text or '')))


def check_rewrite(original, candidate):
    """(ok, reason). False means: print the publisher's headline instead."""
    text = sanitize_headline(candidate)
    if not text:
        return False, 'empty'
    source = '%s %s' % (original.get('title') or '', original.get('snippet') or '')
    invented = _numbers(text) - _numbers(source)
    if invented:
        return False, 'number'
    if len(text) > MAX_HEADLINE:
        return False, 'length'
    if len(text) > max(len(source.strip()) * LENGTH_RATIO, 90):
        return False, 'length'
    return True, ''


def compose_persona(persona_id, stories, model, limit=12):
    """Rewrite up to *limit* headlines. *model* takes chat messages and returns the headline text.

    A persona never blocks the paper: any failure leaves the publisher's headline in place and
    says why, so the edition still prints.
    """
    persona = _persona(persona_id)  # unknown persona is a programming error, not a story failure
    out = []
    for story in list(stories)[:limit]:
        original = str(story.get('title') or '').strip()
        entry = {'title': original, 'styled': original, 'ok': False, 'persona': persona['name'], 'reason': ''}
        if not original:
            entry['reason'] = 'empty'
            out.append(entry)
            continue
        try:
            candidate = model(build_prompt(persona_id, story))
        except Exception as exc:  # upstream failure must not cost the reader the story
            entry['reason'] = str(exc) or exc.__class__.__name__
            out.append(entry)
            continue
        ok, reason = check_rewrite(story, candidate)
        if ok:
            entry['styled'] = sanitize_headline(candidate)
            entry['ok'] = True
        else:
            entry['reason'] = reason
        out.append(entry)
    return out
