# Extracted from fulcra-api-python 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
"""Messages between agents on different Fulcra accounts.

Implements the protocol of the ``connect-our-agents`` skill
(https://github.com/fulcradynamics/agent-skills): each contact in a connection
has their own channel, a v1 ``Event/<uuid>`` data type with the fields in
``CHANNEL_FIELDS``, and shares exactly that channel with everyone else in the
connection through a datashare named ``connect-our-agents: ...``. A message is
one record on the sender's own channel.

Like ``records``, this module sits between the transport (``core``) and the
front-ends (the CLI, the MCP server): functions take a ``FulcraAPI`` as their
first argument, return plain data, and raise plain ``ValueError``.
"""
import datetime
from urllib.error import HTTPError
from uuid import UUID, uuid4
import jsonschema
import jsonschema.exceptions
SHARE_NAME_PREFIX = 'connect-our-agents'
LEGACY_SHARE_NAME_PREFIXES = ('connect-agents-with-anyone',)
CHANNEL_FIELDS = {'properties': {'sender': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'description': 'Name of the agent contact that wrote the message'}, 'kind': {'type': 'string', 'enum': ['message', 'reply', 'ack'], 'description': 'message starts something; reply answers one; ack says you have read one'}, 'body': {'type': 'string', 'minLength': 1, 'maxLength': 4000, 'description': 'The message text'}, 'recipients': {'type': 'array', 'minItems': 1, 'maxItems': 32, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 128}, 'description': 'Agent names the message is for; leave out for everyone in the connection'}, 'topic': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'description': 'Short thread name; replies reuse it'}, 'in_reply_to': {'type': 'string', 'format': 'uuid', 'description': 'The id of the message being answered or acknowledged'}, 'priority': {'type': 'string', 'enum': ['P1', 'P2', 'P3'], 'description': 'P1 urgent, P2 normal, P3 low'}, 'artifacts': {'type': 'array', 'maxItems': 32, 'description': 'Files the message points to, shared separately', 'items': {'type': 'object', 'required': ['path'], 'properties': {'path': {'type': 'string', 'minLength': 1}, 'version': {'type': 'string', 'minLength': 1, 'description': 'File version or content hash, if it matters which one'}, 'owner': {'type': 'string', 'format': 'uuid', 'description': 'Fulcra user ID of the account holding the file, if not the sender'}}}}}, 'required': ['sender', 'kind', 'body']}
MAX_BODY = CHANNEL_FIELDS['properties']['body']['maxLength']
PRIORITIES = tuple(CHANNEL_FIELDS['properties']['priority']['enum'])
REPLY_LOOKBACK = datetime.timedelta(days=30)

def _uuid(value: str, what: str) -> str:
    try:
        return str(UUID(value)).lower()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f'{what} must be a UUID, got {value!r}.')

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
