# Extracted from fulcra_api 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
from uuid import UUID, uuid4
import jsonschema
import jsonschema.exceptions
SHARE_NAME_PREFIX = 'connect-our-agents'
LEGACY_SHARE_NAME_PREFIXES = ('connect-agents-with-anyone',)
CHANNEL_FIELDS = {'properties': {'sender': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'description': 'Name of the agent contact that wrote the message'}, 'kind': {'type': 'string', 'enum': ['message', 'reply', 'ack'], 'description': 'message starts something; reply answers one; ack says you have read one'}, 'body': {'type': 'string', 'minLength': 1, 'maxLength': 4000, 'description': 'The message text'}, 'recipients': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 128}, 'description': 'Agent names the message is for; leave out for everyone in the connection'}, 'topic': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'description': 'Short thread name; replies reuse it'}, 'in_reply_to': {'type': 'string', 'format': 'uuid', 'description': 'The id of the message being answered or acknowledged'}, 'priority': {'type': 'string', 'enum': ['P1', 'P2', 'P3'], 'description': 'P1 urgent, P2 normal, P3 low'}, 'artifacts': {'type': 'array', 'maxItems': 32, 'description': 'Files the message points to, shared separately', 'items': {'type': 'object', 'required': ['path'], 'properties': {'path': {'type': 'string', 'minLength': 1}, 'version': {'type': 'string', 'minLength': 1, 'description': 'File version or content hash, if it matters which one'}, 'owner': {'type': 'string', 'format': 'uuid', 'description': 'Fulcra user ID of the account holding the file, if not the sender'}}}}}, 'required': ['sender', 'kind', 'body']}
MAX_BODY = CHANNEL_FIELDS['properties']['body']['maxLength']

def _uuid(value: str, what: str) -> str:
    try:
        return str(UUID(value)).lower()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f'{what} must be a UUID, got {value!r}.')

def _channel_id(value: str) -> str | None:
    base, sep, rest = value.partition('/')
    if not sep or base.lower() != 'event':
        return None
    try:
        return f'Event/{UUID(rest)}'
    except ValueError:
        return None

def _is_connection_share(share: dict) -> bool:
    return (share.get('datashare_name') or '').startswith((SHARE_NAME_PREFIX, *LEGACY_SHARE_NAME_PREFIXES))

def _channels(share: dict) -> list[str]:
    return [c for t in share.get('fulcra_data_types') or [] if (c := _channel_id(t))]

def resolve_connection(outgoing_shares: list[dict], connection: str) -> tuple[str, list[str]]:
    shares = [s for s in outgoing_shares if _is_connection_share(s)]

    def people(channel: str) -> list[str]:
        found = []
        for share in shares:
            if channel in _channels(share):
                for p in share.get('permissions') or []:
                    if (user := p.get('allowed_fulcra_userid')) and user.lower() not in found:
                        found.append(user.lower())
        return found
    channel = _channel_id(connection)
    if channel is not None:
        with_people = people(channel)
        if not with_people:
            raise ValueError(f"None of your '{SHARE_NAME_PREFIX}: ...' shares includes {channel}. Use your own channel's ID, after sharing it with the other person.")
        return (channel, with_people)
    try:
        user = _uuid(connection, 'connection')
    except ValueError:
        raise ValueError(f"connection must be your channel's ID (Event/<uuid>) or the other person's Fulcra user ID, got {connection!r}.")
    candidates = []
    for share in shares:
        users = {(p.get('allowed_fulcra_userid') or '').lower() for p in share.get('permissions') or []}
        if user in users:
            candidates += [c for c in _channels(share) if c not in candidates]
    if not candidates:
        raise ValueError(f"None of your channels is shared with {user} through a '{SHARE_NAME_PREFIX}: ...' share. Create a channel and share it with them first.")
    if len(candidates) > 1:
        raise ValueError(f"More than one of your channels is shared with {user}: {', '.join(candidates)}. Give the channel's ID instead.")
    return (candidates[0], people(candidates[0]))

def build_message(*, sender: str, body: str, kind: str='message', topic: str | None=None, recipients: list[str] | None=None, priority: str | None=None, in_reply_to: str | None=None, record_id: str | None=None, sources: list[str] | None=None) -> dict:
    if kind not in ('message', 'reply', 'ack'):
        raise ValueError(f'kind must be message, reply or ack, got {kind!r}.')
    if kind == 'message' and in_reply_to is not None:
        raise ValueError('A message that answers another one is a reply or an ack.')
    if kind != 'message' and in_reply_to is None:
        article = 'An' if kind == 'ack' else 'A'
        raise ValueError(f'{article} {kind} needs the id of the message it answers.')
    if not (sender or '').strip():
        raise ValueError("The sender (your agent's name) is required.")
    if not (body or '').strip():
        raise ValueError('The message is empty.')
    if len(body) > MAX_BODY:
        raise ValueError(f'The message is {len(body)} characters; the most is {MAX_BODY}. Put longer content in a file, share it with the same people, and send a short message about it.')
    record: dict = {'id': _uuid(record_id, 'record_id') if record_id else str(uuid4()), 'sender': sender, 'kind': kind, 'body': body}
    if in_reply_to is not None:
        record['in_reply_to'] = _uuid(in_reply_to, 'The id of the message being answered')
    if topic is not None:
        record['topic'] = topic
    if recipients:
        record['recipients'] = list(recipients)
    if priority is not None:
        record['priority'] = priority
    if sources:
        record['sources'] = list(sources)
    fields = {k: v for k, v in record.items() if k not in ('id', 'sources')}
    validator = jsonschema.Draft202012Validator({'type': 'object', **CHANNEL_FIELDS, 'additionalProperties': False}, format_checker=jsonschema.FormatChecker())
    if (error := jsonschema.exceptions.best_match(validator.iter_errors(fields))):
        where = '.'.join((str(p) for p in error.absolute_path))
        raise ValueError(f"{(where + ': ' if where else '')}{error.message}")
    return record
