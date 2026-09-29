"""Local literal rules and a fail-closed main-loop execution boundary."""
import re
import json
from . import updates
from .redaction_payload import redact_request, restore_response, refusal

KEY = 'redaction.v1'
ERROR = 'Error: invalid or conflicting redaction rules; no changes made.'
HELP = ('/fulcra redact add PHRASE [= alias], PHRASE [--profile]\n'
        '/fulcra redact remove PHRASE, PHRASE [--profile]\n'
        '/fulcra redact list|on|off [--profile]\n'
        'Session scope by default; --profile explicitly selects the active profile. '
        'Redact on/off toggles outbound redaction and completed restoration together. '
        'Remove exact originals only, atomically within the selected scope; retired tokens cannot be reused. '
        'List displays original phrases and tokens in shared chat/history; not guaranteed private. '
        'Removing rules may expose original historical text on the next call. '
        'Exact case-sensitive literals; commas and equals are separators (no quoting). '
        'Rules are local, not encrypted. Redaction off permits raw history to be sent. '
        'See docs/redaction.md for scope and limits.')


def empty_scope():
    return {'enabled': False, 'entries': []}


class Redaction:
    def __init__(self, ctx):
        self.ctx = ctx

    def load(self):
        data = self.ctx.state.get(KEY, {'next': 1, 'profile': empty_scope(), 'sessions': {}})
        if type(data) is not dict or type(data['next']) is not int or data['next'] < 1:
            raise ValueError('Invalid state')
        if type(data['sessions']) is not dict or any(not isinstance(k, str) or not k for k in data['sessions']):
            raise ValueError('Invalid state')
        reserved = data.get('reserved', [])  # Older local state has no retired tokens.
        if type(reserved) is not list or any(
            not isinstance(t, str) or not re.fullmatch(r'\{REDACTED-[\w -]+\}', t) for t in reserved
        ) or len(set(reserved)) != len(reserved):
            raise ValueError('Invalid reservations')
        phrases, tokens = set(), set(reserved)
        for scope in [data['profile'], *data['sessions'].values()]:
            inherited = scope is not data['profile'] and scope['enabled'] is None
            if type(scope['enabled']) is not bool and not inherited:
                raise ValueError('Invalid state')
            if type(scope['entries']) is not list:
                raise ValueError('Invalid state')
            for phrase, token in scope['entries']:
                if not isinstance(phrase, str) or not phrase or '{REDACTED-' in phrase:
                    raise ValueError('Invalid state')
                if not isinstance(token, str) or not re.fullmatch(r'\{REDACTED-[\w -]+\}', token):
                    raise ValueError('Invalid state')
                if phrase in phrases or token in tokens:
                    raise ValueError('Invalid state')
                phrases.add(phrase)
                tokens.add(token)
        if any(p in t for p in phrases for t in tokens) or data['next'] <= len(phrases):
            raise ValueError('Invalid state')
        if any(t[10:-1].isdecimal() and int(t[10:-1]) >= data['next'] for t in tokens):
            raise ValueError('Invalid counter')
        return data

    def rules(self, session_id):
        data = self.load()
        profile = data['profile']
        session = data['sessions'].get(session_id)
        scopes = [profile] if session is None else [profile, session]
        enabled = profile['enabled'] if session is None or session['enabled'] is None else session['enabled']
        return {'enabled': enabled,
                'entries': [entry for s in scopes if s['enabled'] for entry in s['entries']]}

    def command(self, raw, session_id=''):
        try:
            text = raw.strip()
            profile = text.endswith(' --profile')
            if profile:
                text = text[:-10].rstrip()
            action, _, value = text.partition(' ')
            value = value.strip()
            if action != 'redact':
                return ERROR
            if value in ('', 'help', '--help'):
                return HELP
            subcommand, _, value = value.partition(' ')
            value = value.strip()
            if subcommand not in ('add', 'remove', 'list', 'on', 'off') or (subcommand not in ('add', 'remove') and value):
                return ERROR
            if not profile and not session_id:
                return 'Error: concrete session ID unavailable; use explicit --profile scope or a supported session surface.'
            with updates._lock(self.ctx):
                data = self.load()
                default = {**empty_scope(), 'enabled': None}
                # Listing neither stores an override nor acknowledges a boundary.
                if subcommand == 'list':
                    scope = data['profile'] if profile else data['sessions'].get(session_id, default)
                    lines = ['Selected scope: ' + ('profile' if profile else 'session'), self.status(scope)]
                    lines += [json.dumps(p, ensure_ascii=True) + ' -> ' + t for p, t in scope['entries']]
                    if not profile:
                        lines += ['Inherited profile rules: ' + self.status(data['profile'])]
                        lines += [json.dumps(p, ensure_ascii=True) + ' -> ' + t for p, t in data['profile']['entries']]
                    lines += ['Warning: originals shown in shared chat/history; not guaranteed private.']
                    return '\n'.join(lines)
                scope = data['profile'] if profile else data['sessions'].setdefault(session_id, default)
                if subcommand in ('on', 'off'):
                    scope['enabled'] = subcommand == 'on'
                elif subcommand == 'remove':
                    phrases = {part.strip() for part in value.split(',')}
                    if not phrases or not phrases <= {p for p, _ in scope['entries']}:
                        raise ValueError('Unknown rule')
                    retired = [t for p, t in scope['entries'] if p in phrases]
                    data.setdefault('reserved', []).extend(retired)
                    scope['entries'] = [e for e in scope['entries'] if e[0] not in phrases]
                elif subcommand == 'add':
                    existing = [e for s in [data['profile'], *data['sessions'].values()] for e in s['entries']]
                    for part in value.split(','):
                        phrase, sep, alias = part.strip().partition('=')
                        phrase, alias = phrase.strip(), alias.strip()
                        if not phrase or '{REDACTED-' in phrase or '--' in phrase:
                            raise ValueError('Invalid rule')
                        if sep and (not re.fullmatch(r'[\w][\w -]{0,63}', alias) or alias.isdecimal()):
                            raise ValueError('Invalid alias')
                        token = '{REDACTED-' + (alias if sep else str(data['next'])) + '}'
                        if token in data.get('reserved', []) or any(phrase == p or token == t for p, t in existing):
                            raise ValueError('Collision')
                        entry = [phrase, token]
                        scope['entries'].append(entry)
                        existing.append(entry)
                        data['next'] += 1
                    if any(p in t for p, _ in existing for t in [e[1] for e in existing] + data.get('reserved', [])):
                        raise ValueError('Placeholder collision')
                    scope['enabled'] = True
                else:
                    raise ValueError('Invalid command')
                self.ctx.state.set(KEY, data)
                if subcommand == 'remove':
                    return (f'{len(retired)} phrases removed. ' + self.status(scope) +
                            ' Removing rules may expose original historical text on the next call.')
                return self.status(scope)
        except Exception:
            # Neither values nor exception details belong in command output/logs.
            return ERROR

    def execute(self, request, next_call, session_id='', api_mode='chat_completions', **kwargs):
        try:
            with updates._lock(self.ctx):
                data = self.load()
                if (not isinstance(session_id, str) or not session_id) and any(
                    s['enabled'] for s in [data['profile'], *data['sessions'].values()]
                ):
                    raise ValueError('Missing session identity')
                session = data['sessions'].get(session_id)
                if (session is None or session['enabled'] is None) and any(
                    s['enabled'] and s['entries'] for s in data['sessions'].values()
                ):
                    # No verified lineage API: never guess continuation or copy
                    # another session's phrases, even when profile rules exist.
                    return refusal('unknown outbound session boundary; explicitly use session redact on/off '
                                   'or add session rules; no provider call was made.')
                rules = self.rules(session_id)
            count = 0
            if not rules['enabled']:
                prepared = None
            else:
                if not isinstance(session_id, str) or not session_id:
                    raise ValueError('Missing session identity')
                if api_mode not in ('chat_completions', 'anthropic_messages', 'codex_responses', 'bedrock_converse'):
                    raise ValueError('Unsupported transport')
                prepared, count = redact_request(request, rules['entries'])
        except Exception:
            return refusal('request validation failed; no provider call was made.')
        if prepared is None:
            return next_call(request)
        # Keep downstream exceptions OUTSIDE the privacy guard. Hermes propagates them once.
        response = next_call(prepared)
        try:
            return restore_response(response, rules['entries'], count)
        except Exception:
            return refusal('completed response could not be safely restored; response withheld.')

    @staticmethod
    def status(scope):
        enabled = 'inherit' if scope['enabled'] is None else 'on' if scope['enabled'] else 'off'
        return (f"Redaction {enabled}; {len(scope['entries'])} phrases. "
                'Outbound redaction and completed restoration toggle together. Changes apply on the next call; '
                'rule/toggle changes can invalidate provider caches. Redaction off permits raw history. '
                'Local main-loop text protection only; see /fulcra redact help.')
