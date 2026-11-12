"""Hermes tool schemas over native Fulcra operations."""
import functools
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from uuid import uuid4

from .client import AuthenticationRequired, client, auth_start, auth_finish
from ._vendor.fulcra_api.connections import CHANNEL_FIELDS, resolve_connection
from ._vendor.fulcra_api.data_type_management import archive_data_type, create_data_type, restore_data_type
from ._vendor.fulcra_api.records import get_records
from ._vendor.fulcra_mcp.agent_invitations import create, match, standing
from ._vendor.fulcra_mcp.connection import send

TOOL_SCHEMAS = {}
STRING = {'type': 'string', 'minLength': 1}
BOOLEAN = {'type': 'boolean'}
UUID_PATTERN = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
UUID = {'type': 'string', 'pattern': '^' + UUID_PATTERN + '$'}
DATA_TYPE = {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_.-]*(?:/' + UUID_PATTERN + r')?$'}
REMOTE_PATH = {'type': 'string', 'pattern': r'^/[^\x00]*$'}
TIMES = {'start_time': STRING, 'end_time': STRING}
ANNOTATIONS = ('moment', 'duration', 'boolean', 'numeric', 'scale')


class LocalError(RuntimeError):
    """Safe plugin-authored diagnostic, never raw transport text."""


def _array(items=STRING, minimum=1):
    return {'type': 'array', 'items': items, 'minItems': minimum}


def _enum(*values):
    return {'type': 'string', 'enum': list(values)}


def error_text(exc):
    # Never interpolate network errors, bodies, URLs, credentials or payloads.
    if isinstance(exc, AuthenticationRequired):
        return ('Error: You are not signed in to Fulcra. Call fulcra_auth, share verification_uri '
                'and user_code with the user, then call fulcra_auth_device after they approve. '
                'Verify any earlier writes before retrying them.')
    if isinstance(exc, HTTPError):
        return f'Error: Fulcra HTTP {exc.code}; writes may have completed. Verify before retrying.'
    if isinstance(exc, LocalError):
        return 'Error: ' + str(exc)
    return 'Error: ' + type(exc).__name__ + ': outcome uncertain; verify writes before retrying.'


def _tool(name, description, properties, required=()):
    TOOL_SCHEMAS[name] = {'description': description, 'parameters': {
        'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}}

    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(args, **kwargs):
            try:
                value = fn(args)
                return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
            except Exception as exc:
                if name.startswith('fulcra_auth'):
                    return 'Error: Authentication failed; secrets and server diagnostics withheld.'
                return error_text(exc)
        return wrapped
    return decorate


def explained(fn, *args, **kwargs):
    """Upstream workflows raise ValueError with messages meant for the caller."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise LocalError(str(exc)) from None


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        result = None
    if result is None or result.utcoffset() is None:
        raise LocalError('Times must be ISO 8601 with a timezone.')
    return result


def resolve(api, data_type, api_version=None, user_id=None, *, write=False):
    entries = api.resolve_data_type(data_type, api_version, api.get_fulcra_userid() if write else user_id)
    if write:
        entries = [e for e in entries if e.get('recordable') and e['api_version'] != 'v0']
    if len(entries) != 1:
        raise LocalError('Select one unambiguous catalog entry with api_version; writes require a recordable type.')
    return entries[0]


def records(api, data_type, start_time=None, end_time=None, user_id=None, api_version=None, latest=False):
    return get_records(api, resolve(api, data_type, api_version, user_id), start_time, end_time, latest=latest)


def record(api, data_type, rows, api_version=None, *, deletion=False):
    entry = resolve(api, data_type, api_version, write=True)
    base, _, annotation = entry['id'].partition('/')
    rows = [dict(row) for row in rows]
    record_type = entry['id'] if entry['api_version'] == 'v1' else base
    for row in rows:
        if deletion:
            row['data_type'] = record_type
        elif annotation and base.endswith('Annotation'):
            source = 'com.fulcradynamics.annotation.' + annotation.lower()
            row['sources'] = [s for s in row.get('sources', []) if s != source] + [source]
    if errors := api.validate_records('DeletedRecord' if deletion else entry['id'], rows, entry['api_version']):
        raise LocalError(f'Record {errors[0][0] + 1} does not match the catalog schema.')
    return api.record_data_type('DeletedRecord' if deletion else record_type, rows, entry['api_version'])


@_tool('fulcra_auth', 'Start browser sign-in. Show the user only verification_uri and user_code. Credentials are shared by every Hermes profile of this OS user.', {})
def fulcra_auth(args):
    return auth_start()


@_tool('fulcra_auth_device', 'After the user approves in the browser, exchange device_code once. If pending, wait retry_after seconds before calling again.', {'device_code': STRING}, ('device_code',))
def fulcra_auth_device(args):
    return auth_finish(args['device_code'])


@_tool('fulcra_user_info', 'Read your Fulcra user ID and name. Names and email addresses are not routing IDs.', {})
def fulcra_user_info(args):
    return client().get_user_info()


# Agent messaging

@_tool('fulcra_create_agent_invitation', "Create an invitation the user can give one person to connect their agents: a new outbox labeled for them and a saved secure code. Optional recipient_userid shares only that outbox with that exact user now. Returns the details for the invitation text; sends nothing. Don't retry an uncertain result; inspect the catalog and shares instead.", {'inviter_name': STRING, 'recipient_name': STRING, 'recipient_userid': UUID}, ('inviter_name', 'recipient_name'))
def fulcra_create_agent_invitation(args):
    return explained(create, client(), **args)


@_tool('fulcra_standing_agent_invitation', "Get the user's reusable open invitation, creating it on first use. Anyone who answers it gets their own outbox; the template itself is never shared. inviter_name saves the name shown in the invitation text; an empty string clears it.", {'inviter_name': {'type': 'string', 'maxLength': 80}})
def fulcra_standing_agent_invitation(args):
    return explained(standing, client(), args.get('inviter_name'))


@_tool('fulcra_match_agent_invitations', "Complete invitations the user prepared: when an incoming channel's first message carries an invitation's exact code, share that invitation's outbox (or a new individual outbox, for open invitations) with the channel's owner. Sends no messages; never retries an uncertain share.", {})
def fulcra_match_agent_invitations(args):
    return match(client())


@_tool('fulcra_send_agent_message', 'Send a message, reply or acknowledgement on an existing connection. Everyone the channel is shared with can read it; recipients are agent names for routing, not access control. "posted" means read back from your own channel, not delivered. Keep record_id: retry an uncertain send only with the same ID and content, and never after a denial.', {
    'connection': {**STRING, 'description': 'Your Event/<uuid> channel, or the peer user ID when exactly one channel is shared with them.'},
    'sender': {**STRING, 'maxLength': 128, 'description': 'Your stable agent name.'},
    'body': {**STRING, 'maxLength': 4000},
    'topic': {**STRING, 'maxLength': 128, 'description': 'Thread name; defaults to chat.'},
    'recipients': {**_array(), 'description': 'Agent names; omit for everyone.'},
    'priority': _enum('P1', 'P2', 'P3'),
    'reply_to': {**UUID, 'description': 'Peer record ID this answers; not looked up.'},
    'ack': {**UUID, 'description': 'Peer record ID this acknowledges; not looked up.'},
    'record_id': UUID,
    'artifacts': CHANNEL_FIELDS['properties']['artifacts'],
    'expected_peer_userids': {**_array(UUID), 'maxItems': 32, 'uniqueItems': True,
                              'description': 'Every other user in the connection; required for multiparty channels.'},
    'target_peer_userid': {**UUID, 'description': 'The peer whose message a reply or ack answers.'},
}, ('connection', 'sender', 'body'))
def fulcra_send_agent_message(args):
    mid = args.get('record_id') or str(uuid4())
    if 'reply_to' in args and 'ack' in args:
        raise LocalError('Give reply_to or ack, not both.')
    api = client()
    # Exact narrow channel grants route the message; send() rechecks the audience.
    shares = [dict(s, datashare_name='connect-our-agents') for s in api.get_datashares()
              if not s.get('share_all_data') and len(s.get('fulcra_data_types') or []) == 1
              and re.fullmatch('Event/' + UUID_PATTERN, s['fulcra_data_types'][0])]
    channel, people = explained(resolve_connection, shares, args['connection'])
    expected = args.get('expected_peer_userids')
    if len(people) != 1 and (expected is None or not args['connection'].startswith('Event/')):
        raise LocalError('Multiparty sends need your exact channel and expected_peer_userids.')
    peer = args.get('target_peer_userid', people[0])
    if peer not in people:
        raise LocalError('target_peer_userid is not in this channel.')
    return send(api, peer_userid=peer, outbox=channel, sender=args['sender'], body=args['body'], mid=mid,
                recipients=args.get('recipients'), pri=args.get('priority', 'P2'), slug=args.get('topic'),
                kind='reply' if 'reply_to' in args else 'ack' if 'ack' in args else 'message',
                in_reply_to=args.get('reply_to', args.get('ack')), artifacts=args.get('artifacts'),
                expected_peer_userids=expected)


# Shares

@_tool('fulcra_list_shares', 'List shares other users give you (incoming, with grant_id) and shares you give (outgoing, with datashare_id).', {'direction': _enum('incoming', 'outgoing', 'both')})
def fulcra_list_shares(args):
    api = client()
    direction = args.get('direction', 'both')
    result = {'own_userid': api.get_fulcra_userid()}
    if direction in ('incoming', 'both'):
        result['incoming'] = api.get_shared_datasets()
    if direction in ('outgoing', 'both'):
        result['outgoing'] = api.get_datashares()
    return result


SELECTORS = {'data_types': _array(DATA_TYPE, 0), 'files': _array(REMOTE_PATH, 0)}
RECIPIENTS = {'user_ids': _array(UUID, 0), 'group_ids': _array(UUID, 0)}
SHARE_TIMES = {k: {'type': ['string', 'null']} for k in TIMES}
SHARE_FIELDS = {'name': 'datashare_name', 'user_ids': 'allowed_user_ids', 'group_ids': 'allowed_group_ids',
                'share_all': 'share_all_data', 'start_time': 'time_start', 'end_time': 'time_end'}


def share_fields(args):
    fields = {SHARE_FIELDS[k]: v for k, v in args.items() if k in SHARE_FIELDS}
    if 'data_types' in args or 'files' in args:
        # Replacements are complete, so concurrent edits cannot merge partially.
        if not all(k in args for k in SELECTORS):
            raise LocalError('Supply both data_types and files to replace selectors (empty lists allowed).')
        if args.get('share_all'):
            raise LocalError('share_all conflicts with selectors.')
        fields['fulcra_data_types'] = args['data_types'] + ['file:' + p for p in args['files']]
        fields['share_all_data'] = False
    return fields


@_tool('fulcra_create_share', 'Give explicit users or groups read access to explicit data_types and files, or everything with share_all=true. File paths and prefixes include future files; / is all files. Time bounds never limit files. Read outgoing shares back afterwards.', {'name': STRING, **SELECTORS, **RECIPIENTS, 'share_all': BOOLEAN, **SHARE_TIMES}, ('name',))
def fulcra_create_share(args):
    if not (args.get('user_ids') or args.get('group_ids')):
        raise LocalError('Explicit recipients required.')
    if bool(args.get('data_types') or args.get('files')) == bool(args.get('share_all')):
        raise LocalError('Choose explicit data_types/files OR share_all=true.')
    if not args.get('share_all'):
        args = {'data_types': [], 'files': [], **args}
    return client().create_datashare(**{'fulcra_data_types': [], 'share_all_data': False, 'allowed_user_ids': [],
                                         'allowed_group_ids': [], **share_fields(args)})


@_tool('fulcra_update_share', 'Replace only the supplied fields of an outgoing share. Changing selectors needs both data_types and files and turns off share_all. Recipient lists replace independently; [] clears. Read outgoing shares before and after.', {'share_id': UUID, 'name': STRING, **SELECTORS, **RECIPIENTS, 'share_all': BOOLEAN, **SHARE_TIMES}, ('share_id',))
def fulcra_update_share(args):
    if not (fields := share_fields(args)):
        raise LocalError('Specify a change.')
    return client().update_datashare(args['share_id'], **fields)


@_tool('fulcra_delete_share', "End a share: an outgoing datashare_id revokes every recipient's access; an incoming user grant_id gives up access someone shared with you. Data stays in place.", {'share_id': UUID}, ('share_id',))
def fulcra_delete_share(args):
    api = client()
    if any(s.get('datashare_id') == args['share_id'] for s in api.get_datashares()):
        return api.delete_datashare(args['share_id'])
    if any(s.get('grant_id') == args['share_id'] and s.get('grant_type') == 'user' for s in api.get_shared_datasets()):
        return api.delete_dataset_permission(args['share_id'])
    raise LocalError('No outgoing share or individual incoming grant has that ID; leave group grants by leaving the group.')


@_tool('fulcra_shared_data_types', "Check which data types another user shares with you over a window before reading their records. all_data_types=true with empty types means everything. Files aren't listed.", {'user_id': UUID, **TIMES}, ('user_id', *TIMES))
def fulcra_shared_data_types(args):
    return client().list_shared_data_types(args['user_id'], args['start_time'], args['end_time'])


# Data types and records

@_tool('fulcra_data_catalog', "Find exact data type IDs and API versions, yours or a sharing user's.", {'data_type': DATA_TYPE, 'category': STRING, 'user_id': UUID})
def fulcra_data_catalog(args):
    return client().v1_catalog(**{('fulcra_userid' if k == 'user_id' else k): v for k, v in args.items()})


@_tool('fulcra_data_type_schema', 'Read the record schema of a data type before writing records.', {'data_type': DATA_TYPE, 'api_version': STRING, 'user_id': UUID}, ('data_type',))
def fulcra_data_type_schema(args):
    api = client()
    entry = resolve(api, **args)
    return api.v1_catalog_schema(entry['id'], entry['api_version'], entry['fulcra_userid'])


@_tool('fulcra_create_data_type', 'Create a data type to record into. Prefer event (something that happens) or metric (a measured number); both take custom fields as JSON Schema. Annotation bases (moment, duration, boolean, numeric, scale) take no fields; scale needs five scale_labels.', {
    'base_type': _enum('event', 'metric', *ANNOTATIONS), 'name': STRING, 'description': STRING,
    'fields': {'type': 'object', 'description': 'event/metric: {"properties": {...}, "required": [...]}'},
    'unit': STRING, 'metric_kind': _enum('cumulative', 'discrete'),
    'scale': {'type': 'object', 'description': 'metric: {"min": 1, "max": 10, "step": 1}'},
    'value_map': {'type': 'object', 'description': 'metric: labels for integer values'},
    'tags': _array(), 'default_value': STRING, 'scale_labels': {**_array(), 'minItems': 5, 'maxItems': 5},
}, ('base_type', 'name'))
def fulcra_create_data_type(args):
    api = client()
    base = args['base_type'].capitalize() + ('Annotation' if args['base_type'] in ANNOTATIONS else '')
    return explained(create_data_type, api, resolve(api, base), args['name'], description=args.get('description'),
                     unit=args.get('unit'), aggregation=args.get('metric_kind'), scale=args.get('scale'),
                     value_map=args.get('value_map'), fields_schema=args.get('fields'), tags=args.get('tags'),
                     raw_value=args.get('default_value'), scale_labels=args.get('scale_labels'))


def _owned(api, data_type):
    own = api.get_fulcra_userid()
    entries = api.v1_catalog(data_type=data_type, fulcra_userid=own)
    if len(entries) != 1 or entries[0].get('fulcra_userid') != own or not entries[0].get('recordable'):
        raise LocalError('An owned recordable Event or Metric type is required.')
    return entries[0]


def _folded(text):
    # The catalog folds description whitespace.
    return ' '.join((text or '').split())


@_tool('fulcra_update_data_type', 'Replace the name or description of your own Event/Metric type. Users it is shared with can read the description. Pass expected_description as last read to reject a stale edit (not atomic). Only verified=true confirms the readback.', {'data_type': DATA_TYPE, 'name': STRING, 'description': {'type': 'string'}, 'expected_description': {'type': 'string'}}, ('data_type',))
def fulcra_update_data_type(args):
    changes = {k: args[k] for k in ('name', 'description') if k in args}
    base, _, type_id = args['data_type'].partition('/')
    if base not in ('Event', 'Metric') or not changes:
        raise LocalError('Give an exact Event/<uuid> or Metric/<uuid> and a name or description.')
    api = client()
    before = _owned(api, args['data_type'])
    if 'expected_description' in args and _folded(before.get('description')) != _folded(args['expected_description']):
        raise LocalError('Description changed; read it again before deciding whether to update.')
    api.update_data_type(base, type_id, changes)
    after = _owned(api, args['data_type'])
    verified = all(_folded(after.get(k)) == _folded(v) for k, v in changes.items())
    return {'status': 'updated' if verified else 'uncertain', 'verified': verified, 'data_type': args['data_type']}


@_tool('fulcra_data_type_lifecycle', 'Archive or restore your own data type. Records are kept.', {'data_type': DATA_TYPE, 'action': _enum('archive', 'restore')}, ('data_type', 'action'))
def fulcra_data_type_lifecycle(args):
    api = client()
    base, _, type_id = args['data_type'].partition('/')
    if base in ('Event', 'Metric'):
        return (archive_data_type if args['action'] == 'archive' else restore_data_type)(api, base, type_id)
    if base.endswith('Annotation') and type_id:
        return (api.delete_annotation if args['action'] == 'archive' else api.restore_annotation)(type_id)
    raise LocalError('Use the full <BaseType>/<uuid> ID.')


@_tool('fulcra_get_records', "Read records between timezone-aware start_time and end_time, or the newest with latest=true (v1 only). user_id reads a sharing user's data. Raw sources can overlap; don't sum blindly.", {'data_type': DATA_TYPE, **TIMES, 'latest': BOOLEAN, 'api_version': STRING, 'user_id': UUID}, ('data_type',))
def fulcra_get_records(args):
    args = dict(args)
    if any(k in args for k in TIMES) if args.get('latest') else not all(k in args for k in TIMES):
        raise LocalError('Supply start_time and end_time, or latest=true.')
    for key in TIMES:
        if key in args:
            args[key] = timestamp(args[key])
    return records(client(), **args)


@_tool('fulcra_record', "Write records to one of your data types after checking them against its schema. Give each record a stable id to correct it later by writing the same id. Accepted is not yet readable; read back before saying it's done.", {'data_type': DATA_TYPE, 'records': _array({'type': 'object'}), 'api_version': STRING}, ('data_type', 'records'))
def fulcra_record(args):
    return record(client(), args['data_type'], args['records'], args.get('api_version'))


@_tool('fulcra_delete_records', 'Delete explicit records by ID from one of your data types. Deletion is asynchronous; read back afterwards.', {'data_type': DATA_TYPE, 'record_ids': _array(UUID), 'api_version': STRING}, ('data_type', 'record_ids'))
def fulcra_delete_records(args):
    return record(client(), args['data_type'], [{'record_id': i} for i in args['record_ids']], args.get('api_version'), deletion=True)


@_tool('fulcra_data_updates', 'Summarize which data types and files changed during a window of processing time (not record time). include_shared also checks users who share with you.', {**TIMES, 'user_id': UUID, 'include_shared': BOOLEAN}, tuple(TIMES))
def fulcra_data_updates(args):
    return client().data_updates(timestamp(args['start_time']), timestamp(args['end_time']),
                                 args.get('user_id'), include_shared=args.get('include_shared', False))


# Files

@_tool('fulcra_file_list', "List a folder of your files, or a sharing user's.", {'path': REMOTE_PATH, 'user_id': UUID})
def fulcra_file_list(args):
    return client().list_files(args.get('path', '/'), fulcra_userid=args.get('user_id'))


@_tool('fulcra_file_stat', 'Read file metadata and earlier version IDs for fulcra_file_restore. A deleted file is not found.', {'path': REMOTE_PATH, 'user_id': UUID}, ('path',))
def fulcra_file_stat(args):
    return client().file_stat(args['path'], args.get('user_id'))


@_tool('fulcra_file_upload', 'Upload UTF-8 content or an absolute local_path to a remote path. Uploading to an existing path adds a version.', {'path': REMOTE_PATH, 'content': {'type': 'string'}, 'local_path': STRING}, ('path',))
def fulcra_file_upload(args):
    if ('content' in args) == ('local_path' in args):
        raise LocalError('Supply content OR local_path.')
    if 'local_path' in args:
        path = Path(args['local_path'])
        if not path.is_absolute() or not path.is_file():
            raise LocalError('local_path must be an absolute regular file.')
        data = path.read_bytes()
    else:
        data = args['content'].encode('utf-8')
    # Signed upload URLs are capabilities, not useful output.
    return {k: v for k, v in client().write_file(args['path'], data).items() if k != 'url'}


@_tool('fulcra_file_download', "Read the latest version of a file as UTF-8 text, or save its bytes to a new absolute local_path. user_id reads a sharing user's file.", {'path': REMOTE_PATH, 'local_path': STRING, 'user_id': UUID}, ('path',))
def fulcra_file_download(args):
    target = Path(args['local_path']) if 'local_path' in args else None
    if target is not None and (not target.is_absolute() or target.exists() or target.is_symlink()):
        raise LocalError('Choose a new absolute local_path; no overwrites.')
    data = client().read_file(args['path'], args.get('user_id'))
    if target is not None:
        with os.fdopen(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
            stream.write(data)
        return {'local_path': str(target), 'bytes': len(data)}
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise LocalError('Binary file: supply local_path.') from None


@_tool('fulcra_file_delete', 'Delete the latest version of one file (not a folder); the path then reads as not found. Earlier versions are kept, so note their IDs with fulcra_file_stat first to restore one later. The deleted version cannot be restored.', {'path': REMOTE_PATH}, ('path',))
def fulcra_file_delete(args):
    api = client()
    return api.delete_file(api.resolve_filepath(args['path'])[0]['id'])


@_tool('fulcra_file_restore', 'Make an earlier version of your file the latest again. Deleted versions cannot be restored.', {'version_id': UUID}, ('version_id',))
def fulcra_file_restore(args):
    return client().restore_file(args['version_id'])
