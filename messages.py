"""Read untrusted messages from contacts' channels, with per-agent cursors."""
import json
from pathlib import Path
import re
from datetime import datetime, timedelta, timezone

UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
OVERLAP = timedelta(minutes=30)
SEEN_LIMIT = 2048
# The connect-our-agents message fields, shared with the skills.
FIELDS = json.loads((Path(__file__).parent / 'skills/connect-our-agents/references/channel-fields.json').read_text())


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp needs a time zone: ' + value)
    return parsed


def valid(value, schema):
    """Whether value fits schema, for the JSON Schema keywords the channel fields use."""
    kind = schema.get('type')
    if kind == 'string':
        return (isinstance(value, str) and schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 1e9)
                and value in schema.get('enum', [value])
                and (schema.get('format') != 'uuid' or re.fullmatch(UUID, value.lower()) is not None))
    if kind == 'array':
        return (isinstance(value, list) and schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 1e9)
                and all(valid(item, schema.get('items', {})) for item in value))
    if kind == 'object' or 'properties' in schema:
        properties = schema.get('properties', {})
        return (isinstance(value, dict) and all(key in value for key in schema.get('required', []))
                and all(valid(v, properties[k]) for k, v in value.items() if k in properties))
    return True


def channels(shares, own):
    """(owner, channel) pairs other users share with you as exactly one Event channel."""
    found = []
    for share in shares:
        types, owner = share.get('data_types') or [], share.get('sharing_fulcra_userid')
        only = len(types) == 1 and not share.get('file_paths') and not share.get('file_history_paths')
        if (only and re.fullmatch('Event/' + UUID, types[0]) and owner and owner != own
                and share.get('share_all_data') is False and (owner, types[0]) not in found):
            found.append((owner, types[0]))
    return found


def outboxes(shares, own):
    """Your own channels, by the contact they're shared with: each outgoing share of exactly one Event."""
    found = {}
    for share in shares:
        types = share.get('data_types') or []
        if (len(types) == 1 and re.fullmatch('Event/' + UUID, types[0]) and not share.get('file_paths')
                and not share.get('file_history_paths') and share.get('share_all_data') is False):
            for peer in share.get('with_user_ids') or []:
                if peer != own and types[0] not in found.setdefault(peer, []):
                    found[peer].append(types[0])
    return found


def _answered(api, own, outboxes, start, now):
    """IDs your agent (in any client) has replied to or acknowledged on these channels of yours."""
    ids = set()
    for outbox in outboxes:
        for row in api.records(outbox, start, now, own):
            if row.get('kind') in ('reply', 'ack') and isinstance(row.get('in_reply_to'), str):
                ids.add(row['in_reply_to'])
    return ids


def _message(row, agent):
    # The API reads unset fields back as null; treat them as absent.
    fields = {k: v for k, v in row.items() if k in FIELDS['properties'] and v is not None}
    if not valid(fields, FIELDS):
        return None
    # Without an agent name, messages addressed to particular agents are kept; the notice shows to whom.
    if agent.strip() and 'recipients' in fields and not {agent, 'all'} & set(fields['recipients']):
        return None
    return {**fields, 'id': row['id'], 'start_time': row.get('start_time')}


def receive(api, own, pairs, agent, cursors, initial, outgoing=()):
    """New messages for agent on these channels since initial or their cursor; updates cursors in place.

    The user has read everything up to the latest message they replied to or acknowledged (in chat, the
    Agents I Know panel or any other client), so those messages and anything older are left out; their IDs
    come back in `read`, to drop from notices already waiting."""
    now = datetime.now(timezone.utc)
    mine = outboxes(outgoing, own)
    messages, read, skipped = [], [], 0
    for owner, channel in pairs:
        key = json.dumps([own, agent, owner, channel])
        previous = cursors.get(key, {})
        start = timestamp(previous['until']) - OVERLAP if previous else initial
        seen = list(previous.get('seen', []))
        rows = api.records(channel, start, now, owner)
        answered = _answered(api, own, mine.get(owner, []), start, now) if mine.get(owner) else set()
        times = [timestamp(r['start_time']) for r in rows
                 if r.get('id') in answered and isinstance(r.get('start_time'), str)]
        read_through = max(times) if times else None
        for row in rows:
            message = _message(row, agent)
            if message is None:
                skipped += 1
            elif read_through and isinstance(row.get('start_time'), str) and timestamp(row['start_time']) <= read_through:
                read.append(message['id'])
                if message['id'] not in seen:
                    seen.append(message['id'])
            elif message['id'] not in seen:
                seen.append(message['id'])
                messages.append({'owner': owner, 'channel': channel, **message})
        cursors[key] = {'until': now.isoformat(), 'seen': seen[-SEEN_LIMIT:]}
    return {'messages': messages, 'read': read, 'skipped_records': skipped}
