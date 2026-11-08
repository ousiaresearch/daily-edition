"""Minimal OpenAI-compatible client for persona rewrites.

Configuration comes from Hermes's profile scope, or the process environment in standalone runs.
If no key is configured the plugin stays offline and the paper prints in the
publisher's own words; nothing is silently faked.
"""

import json
import os
import urllib.error
import urllib.request

# There is deliberately no default endpoint. A public plugin must not route anyone's headlines to a
# vendor they did not choose, so styling stays off until DAILY_EDITION_BASE_URL names one.
DEFAULT_BASE = ''
DEFAULT_MODEL = 'claude-haiku-5.5'
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
MAX_TOKENS = 96
TIMEOUT = 25


def endpoint(base_url):
    base = str(base_url or DEFAULT_BASE).strip().rstrip('/')
    if not base:
        raise ValueError('No model endpoint configured (set DAILY_EDITION_BASE_URL)')
    if '://' not in base:
        base = 'https://' + base
    scheme, _, rest = base.partition('://')
    host = rest.split('/')[0].split(':')[0].lower()
    if scheme not in ('http', 'https'):
        raise ValueError('Only http(s) endpoints are supported')
    if scheme == 'http' and host not in LOOPBACK:
        raise ValueError('Plain http is only allowed for a local endpoint')
    if not base.endswith('/v1'):
        base = base + '/v1'
    return base + '/chat/completions'


def _secret(name, env):
    """Resolve a profile-scoped configuration value without cross-profile fallback.

    Hermes treats scope misses differently for routed and single-profile tasks. Use its routed
    predicate (which also covers foreign-home scopes outside multiplex mode) before any fallback.
    """
    from_env = str(env.get(name) or '').strip()
    try:
        from agent.secret_scope import get_secret, serves_routed_profile
    except ModuleNotFoundError as exc:
        return from_env if exc.name in ('agent', 'agent.secret_scope') else ''
    except Exception:
        return ''
    try:
        scoped = get_secret(name)
        if scoped is not None:
            return str(scoped).strip()
        return '' if serves_routed_profile() else from_env
    except Exception:
        return ''


def settings(env=None):
    env = dict(os.environ if env is None else env)
    key = _secret('DAILY_EDITION_API_KEY', env)
    model = _secret('DAILY_EDITION_MODEL', env) or DEFAULT_MODEL
    base = _secret('DAILY_EDITION_BASE_URL', env)
    if not base:
        return {'configured': False, 'model': model,
                'error': 'No model endpoint configured. Set DAILY_EDITION_BASE_URL for the gateway.'}
    try:
        url = endpoint(base)
    except ValueError as exc:
        return {'configured': False, 'model': model, 'error': str(exc)}
    if not key:
        return {'configured': False, 'model': model,
                'error': 'No model key configured. Set DAILY_EDITION_API_KEY for the gateway.'}
    return {'configured': True, 'model': model, 'url': url, 'error': ''}


def fail(message, key=''):
    text = str(message)
    if key:
        text = text.replace(key, '[redacted]')
    raise RuntimeError(text)


def build_request(messages, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, api_key=''):
    return {
        'url': endpoint(base_url),
        'headers': {'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'},
        'body': {'model': model, 'messages': messages, 'max_tokens': MAX_TOKENS, 'temperature': 0.7},
    }


def chat(messages, config=None):
    config = config or settings()
    try:
        from agent.secret_scope import serves_routed_profile
    except ModuleNotFoundError as exc:
        if exc.name not in ('agent', 'agent.secret_scope'):
            fail('Unable to verify model profile scope')
        routed = False
    except Exception:
        fail('Unable to verify model profile scope')
    else:
        try:
            routed = serves_routed_profile()
        except Exception:
            fail('Unable to verify model profile scope')
    if routed:
        current = settings()
        if not current.get('configured'):
            fail(current.get('error') or 'Model not configured')
        if config.get('url') != current['url'] or config.get('model') != current['model']:
            fail('Model configuration no longer matches the current profile')
    if not config.get('configured'):
        fail(config.get('error') or 'Model not configured')
    key = _secret('DAILY_EDITION_API_KEY', os.environ)
    if not key:
        fail('No model key configured. Set DAILY_EDITION_API_KEY for the gateway.')
    payload = build_request(messages, base_url=config['url'].rsplit('/chat/completions', 1)[0],
                            model=config['model'], api_key=key)
    request = urllib.request.Request(
        payload['url'], data=json.dumps(payload['body']).encode('utf-8'),
        headers=payload['headers'], method='POST')
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = json.loads(response.read(1_000_001).decode('utf-8', 'replace'))
    except urllib.error.HTTPError as exc:
        fail('Model endpoint returned HTTP %s' % exc.code)
    except Exception as exc:
        fail('Model request failed: %s' % exc, key=key)
    try:
        return data['choices'][0]['message']['content']
    except Exception:
        fail('Model endpoint returned an unexpected body')
