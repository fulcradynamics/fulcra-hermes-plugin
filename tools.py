"""Deliberate Hermes schemas over native Fulcra operations."""
import functools
import json
import os

from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

from .client import client, auth_start, auth_finish
from ._vendor.records import get_records
from .output import _bounded_output

TOOL_SCHEMAS = {}
STRING = {'type': 'string', 'minLength': 1}
BOOLEAN = {'type': 'boolean'}
UUID_PATTERN = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
UUID = {'type': 'string', 'pattern': '^' + UUID_PATTERN + '$'}
DATA_TYPE = {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_.-]*(?:/' + UUID_PATTERN + r')?$'}
REMOTE_PATH = {'type': 'string', 'pattern': r'^/[^\x00]*$'}
BASE_TYPES = ['MomentAnnotation', 'DurationAnnotation', 'BooleanAnnotation', 'NumericAnnotation', 'ScaleAnnotation']


class LocalError(RuntimeError):
    """Safe plugin-authored diagnostic, never raw transport text."""


def _array(items=STRING, minimum=1):
    return {'type': 'array', 'items': items, 'minItems': minimum}


def _enum(*values):
    return {'type': 'string', 'enum': list(values)}


def _error_text(exc, device_code=None):
    # Never interpolate network errors, bodies, URLs, credentials or payloads.
    if isinstance(exc, HTTPError):
        return f'Error: Fulcra HTTP {exc.code}; writes may have completed. Verify before retrying.'
    if isinstance(exc, LocalError):
        text = str(exc)
        if device_code:
            text = text.replace(device_code, '[redacted]')
        return 'Error: ' + text
    return 'Error: ' + type(exc).__name__ + ': outcome uncertain; verify writes before retrying.'


def _tool(name, description, properties, required=()):
    schema = {'description': description, 'parameters': {'type': 'object', 'properties': properties,
              'required': list(required), 'additionalProperties': False}}
    TOOL_SCHEMAS[name] = schema
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(args, **kwargs):
            try:
                value = fn(args)
                output = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
                if name.startswith('fulcra_auth') and len(output.encode()) > 16000:
                    return 'Error: Oversized authentication response; not persisted.'
                return _bounded_output(output)
            except Exception as exc:
                if name.startswith('fulcra_auth'):
                    return 'Error: Authentication failed; secrets and server diagnostics withheld.'
                return _bounded_output(_error_text(exc))
        return wrapped
    return decorate


def _timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise LocalError('Times must be ISO8601 with timezone.')
        return result
    except (ValueError, TypeError):
        raise LocalError('Times must be ISO8601 with timezone.') from None


TIMES = {'start_time': STRING, 'end_time': STRING}


def window(args):
    start, end = (_timestamp(args[k]) for k in TIMES)
    if end <= start:
        raise LocalError('end_time must follow start_time.')
    return start, end


def resolve(api, data_type, api_version=None, user_id=None, *, write=False):
    entries = api.resolve_data_type(data_type, api_version, api.get_fulcra_userid() if write else user_id)
    if write:
        entries = [e for e in entries if e.get('recordable') and e['api_version'] != 'v0']
    if len(entries) != 1:
        raise LocalError('Select one unambiguous catalog entry with api_version; writes require a recordable type.')
    return entries[0]


def records(api, data_type, start_time=None, end_time=None, user_id=None, api_version=None, latest=False, group_id=None, participant_id=None):
    if bool(group_id) != bool(participant_id) or (group_id and user_id):
        raise LocalError('Use user_id OR group_id and participant_id together.')
    entry = resolve(api, data_type, api_version, user_id)
    source = api.group_participant(group_id, participant_id) if group_id else api
    return get_records(source, entry, start_time, end_time, latest=latest)


def record(api, data_type, rows, api_version=None, *, deletion=False):
    entry = resolve(api, data_type, api_version, write=True)
    base, _, annotation = entry['id'].partition('/')
    rows = [dict(row) for row in rows]
    target = 'DeletedRecord' if deletion else base
    for row in rows:
        if deletion:
            row['data_type'] = base
        elif annotation:
            source = 'com.fulcradynamics.annotation.' + annotation.lower()
            row['sources'] = [s for s in row.get('sources', []) if s != source] + [source]
    errors = api.validate_records('DeletedRecord' if deletion else entry['id'], rows, entry['api_version'])
    if errors:
        raise LocalError(f'Record {errors[0][0] + 1} does not match the catalog schema.')
    return api.record_data_type(target, rows, entry['api_version'])


@_tool('fulcra_auth', 'Start browser authentication without waiting or resetting credentials. Share only verification_uri/user_code with the human. Credentials are OS-user shared across profiles.', {})
def fulcra_auth(args):
    return auth_start()


@_tool('fulcra_auth_device', 'After browser approval, exchange device_code once. If pending, wait retry_after seconds before another call. No blocking polling; credentials never returned.', {'device_code': STRING}, ('device_code',))
def fulcra_auth_device(args):
    return auth_finish(args['device_code'])


@_tool('fulcra_data_catalog', 'Discover exact data type IDs and API versions before queries/writes.', {'data_type': DATA_TYPE, 'category': STRING, 'user_id': UUID})
def fulcra_data_catalog(args):
    return client().v1_catalog(**{('fulcra_userid' if k == 'user_id' else k): v for k, v in args.items()})


@_tool('fulcra_data_type_schema', 'Read the record schema; api_version disambiguates catalog entries.', {'data_type': DATA_TYPE, 'api_version': STRING, 'user_id': UUID}, ('data_type',))
def fulcra_data_type_schema(args):
    api = client()
    entry = resolve(api, **args)
    return api.v1_catalog_schema(entry['id'], entry['api_version'], entry['fulcra_userid'])


@_tool('fulcra_create_data_type', 'Create an annotation type, not records. Scale needs five labels. Optional defaults are native JSON booleans/numbers; tags create tags.', {'base_type': _enum(*BASE_TYPES), 'name': STRING, 'description': STRING, 'tags': _array(), 'metric_kind': _enum('cumulative', 'discrete'), 'value': {'type': ['number', 'boolean']}, 'unit': STRING, 'scale_labels': {**_array(), 'minItems': 5, 'maxItems': 5}}, ('base_type', 'name'))
def fulcra_create_data_type(args):
    args = dict(args)
    kind = args.pop('base_type').removesuffix('Annotation').lower()
    return client().create_annotation(kind, description=args.pop('description', ''), tags=args.pop('tags', []), **args)


@_tool('fulcra_data_type_lifecycle', 'Archive/restore an explicit user annotation type, not its records.', {'data_type': DATA_TYPE, 'action': _enum('archive', 'restore')}, ('data_type', 'action'))
def fulcra_data_type_lifecycle(args):
    base, _, identifier = args['data_type'].partition('/')
    if base not in BASE_TYPES or not identifier:
        raise LocalError('Use the full BaseAnnotation/UUID ID.')
    api = client()
    return {'archive': api.delete_annotation, 'restore': api.restore_annotation}[args['action']](identifier)


@_tool('fulcra_get_records', 'Read raw records. Supply timezone-aware start_time/end_time OR latest=true (v1 only). Raw sources can overlap; do not sum blindly. Check shared types before another owner query.', {'data_type': DATA_TYPE, **TIMES, 'latest': BOOLEAN, 'api_version': STRING, 'user_id': UUID, 'group_id': UUID, 'participant_id': UUID}, ('data_type',))
def fulcra_get_records(args):
    args = dict(args)
    if args.get('latest'):
        if any(k in args for k in TIMES):
            raise LocalError('latest conflicts with time bounds.')
    else:
        if not all(k in args for k in TIMES):
            raise LocalError('Supply start_time and end_time.')
        args['start_time'], args['end_time'] = window(args)
    return records(client(), **args)


@_tool('fulcra_record', 'Upload explicit records after catalog schema validation. Include tags/sources in each record; annotation source is added, no CLI source. Acceptance is not ingestion; read updates/records afterward.', {'data_type': DATA_TYPE, 'records': _array({'type': 'object'}), 'api_version': STRING}, ('data_type', 'records'))
def fulcra_record(args):
    return record(client(), args['data_type'], args['records'], args.get('api_version'))


@_tool('fulcra_delete_records', 'Delete only explicit record UUIDs. No all-record/time-range deletion. Tombstone acceptance is asynchronous; verify afterward.', {'data_type': DATA_TYPE, 'record_ids': _array(UUID), 'api_version': STRING}, ('data_type', 'record_ids'))
def fulcra_delete_records(args):
    return record(client(), args['data_type'], [{'record_id': i} for i in args['record_ids']], args.get('api_version'), deletion=True)


@_tool('fulcra_data_updates', 'Read processing-time updates, not event-time records.', {**TIMES, 'user_id': UUID}, tuple(TIMES))
def fulcra_data_updates(args):
    return client().data_updates(args['start_time'], args['end_time'], args.get('user_id'))


SELECTORS = {'data_types': _array(DATA_TYPE, 0), 'files': _array(REMOTE_PATH, 0)}
RECIPIENTS = {'user_ids': _array(UUID, 0), 'group_ids': _array(UUID, 0)}
SHARE_TIMES = {k: {'type': ['string', 'null']} for k in TIMES}


def share_fields(args):
    fields = { {'name': 'datashare_name', 'user_ids': 'allowed_user_ids', 'group_ids': 'allowed_group_ids', 'share_all': 'share_all_data', 'start_time': 'time_start', 'end_time': 'time_end'}[k]: v for k, v in args.items() if k in {'name', 'user_ids', 'group_ids', 'share_all', *TIMES}}
    if 'data_types' in args or 'files' in args:
        # Replacements are atomic and deliberately complete; no read/modify/write races.
        if not all(k in args for k in SELECTORS):
            raise LocalError('Supply both data_types and files to replace selectors (empty lists allowed).')
        if args.get('share_all'):
            raise LocalError('share_all conflicts with selectors.')
        fields['fulcra_data_types'] = args['data_types'] + ['file:' + p for p in args['files']]
        fields['share_all_data'] = False
    return fields


@_tool('fulcra_create_share', 'Grant explicit recipients explicit data_types/files OR share_all=true. Group membership is live. File prefixes include future files; / is all files, latest versions only. Time bounds NEVER constrain files. Missing bounds are open. Verify outgoing shares.', {'name': STRING, **SELECTORS, **RECIPIENTS, 'share_all': BOOLEAN, **SHARE_TIMES}, ('name',))
def fulcra_create_share(args):
    if not (args.get('user_ids') or args.get('group_ids')):
        raise LocalError('Explicit recipients required.')
    scoped = bool(args.get('data_types') or args.get('files'))
    if scoped == bool(args.get('share_all')):
        raise LocalError('Choose explicit selectors OR share_all=true.')
    args = dict(args)
    if not args.get('share_all'):
        args.setdefault('data_types', [])
        args.setdefault('files', [])
    fields = share_fields(args)
    fields.setdefault('fulcra_data_types', [])
    fields.setdefault('share_all_data', False)
    fields.setdefault('allowed_user_ids', [])
    fields.setdefault('allowed_group_ids', [])
    return client().create_datashare(**fields)


@_tool('fulcra_update_share', 'Replace only supplied fields. Selector changes require BOTH data_types and files and disable all-data; empty lists clear. Recipient lists independently replace/clear. share_all=true broadens access; null bounds open time-series access, NEVER file access. Read outgoing shares before and after.', {'share_id': UUID, 'name': STRING, **SELECTORS, **RECIPIENTS, 'share_all': BOOLEAN, **SHARE_TIMES}, ('share_id',))
def fulcra_update_share(args):
    fields = share_fields(args)
    if not fields:
        raise LocalError('Specify a change.')
    return client().update_datashare(args['share_id'], **fields)


@_tool('fulcra_list_shares', 'List incoming grants/outgoing shares. grant_id relinquishes a user grant; share_id revokes an outgoing share. Self entry is included.', {'direction': _enum('incoming', 'outgoing', 'both')})
def fulcra_list_shares(args):
    api = client()
    direction = args.get('direction', 'both')
    result = {}
    if direction in ('incoming', 'both'):
        result['incoming'] = api.get_shared_datasets()
    if direction in ('outgoing', 'both'):
        result['outgoing'] = api.get_datashares()
    return result


@_tool('fulcra_delete_share', 'Revoke an explicit outgoing share, all its recipients, not underlying data.', {'share_id': UUID}, ('share_id',))
def fulcra_delete_share(args):
    return client().delete_datashare(args['share_id'])


@_tool('fulcra_leave_share', 'Relinquish an explicit individual incoming grant, not a group grant.', {'grant_id': UUID}, ('grant_id',))
def fulcra_leave_share(args):
    api = client()
    if not any(s.get('grant_id') == args['grant_id'] and s.get('grant_type') == 'user' for s in api.get_shared_datasets()):
        raise LocalError('No matching individual incoming grant.')
    return api.delete_dataset_permission(args['grant_id'])


@_tool('fulcra_shared_data_types', 'Check access before reading shared records. all_data_types=true with empty types means everything. Window must be strictly inside share end. Files are not listed.', {'user_id': UUID, **TIMES}, ('user_id', *TIMES))
def fulcra_shared_data_types(args):
    return client().list_shared_data_types(args['user_id'], args['start_time'], args['end_time'])


@_tool('fulcra_file_upload', 'Upload UTF-8 content OR an existing absolute local_path to an explicit remote path. Existing remote paths create versions. Verify with file_stat.', {'path': REMOTE_PATH, 'content': {'type': 'string'}, 'local_path': STRING}, ('path',))
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
    result = client().write_file(args['path'], data)
    # Signed upload URLs are capabilities, not useful tool output.
    return {k: v for k, v in result.items() if k != 'url'}


@_tool('fulcra_file_download', 'Read latest remote UTF-8 text, or exact bytes to a NEW absolute local_path (no overwrite). Shared owner optional. Large text gets private local artifact.', {'path': REMOTE_PATH, 'local_path': STRING, 'user_id': UUID}, ('path',))
def fulcra_file_download(args):
    target = Path(args['local_path']) if 'local_path' in args else None
    if target is not None and (not target.is_absolute() or target.exists() or target.is_symlink()):
        raise LocalError('Choose a new absolute local_path; no overwrites.')
    data = client().read_file(args['path'], args.get('user_id'))
    if target is not None:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        return {'local_path': str(target), 'bytes': len(data)}
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise LocalError('Binary file: supply local_path.') from None


@_tool('fulcra_file_list', 'List a directory for yourself or an explicit shared owner.', {'path': REMOTE_PATH, 'user_id': UUID})
def fulcra_file_list(args):
    return client().list_files(args.get('path', '/'), fulcra_userid=args.get('user_id'))


@_tool('fulcra_file_stat', 'Read versions/metadata. Shared owners expose latest only; own deleted versions may be restored.', {'path': REMOTE_PATH, 'user_id': UUID}, ('path',))
def fulcra_file_stat(args):
    return client().file_stat(args['path'], args.get('user_id'))


@_tool('fulcra_file_delete', 'Delete only the latest version at an explicit path; not recursive. Retain version IDs for recovery.', {'path': REMOTE_PATH}, ('path',))
def fulcra_file_delete(args):
    api = client()
    files = api.resolve_filepath(args['path'])
    return api.delete_file(files[0]['id'])


@_tool('fulcra_file_restore', 'Restore the exact version UUID from file_stat; verify afterward.', {'version_id': UUID}, ('version_id',))
def fulcra_file_restore(args):
    return client().restore_file(args['version_id'])


@_tool('fulcra_file_share', 'Share explicit file path/prefix with explicit users. Includes future files, latest only; / is all files. No time restriction on files. Verify outgoing shares.', {'path': REMOTE_PATH, 'user_ids': _array(UUID), 'name': STRING}, ('path', 'user_ids', 'name'))
def fulcra_file_share(args):
    return client().create_datashare(args['name'], ['file:' + args['path']], args['user_ids'], share_all_data=False, allowed_group_ids=[])
