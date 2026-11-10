"""Explicit native invitation acceptance and matching.

The public Connection details marker interoperates with other Fulcra agents.
No automatic retries; a consumed invitation cannot authorize another grant.
"""
import copy
import json
import math
import re
import threading

from datetime import datetime, timezone, timedelta
from uuid import uuid4

from . import contacts as c

LOCK = threading.RLock()


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def history(api, owner, channel, entry=None):
    if entry is None:
        entry, = api.v1_catalog(data_type=channel, fulcra_userid=owner)
    end = datetime.now(timezone.utc)
    start = timestamp((entry.get('metadata') or {}).get('created_at')) or end - timedelta(days=365)
    if start >= end:
        return []
    # PromQL durations use integer units; filter both rounded boundaries below.
    anchor = math.ceil(end.timestamp())
    seconds = math.ceil(anchor - start.timestamp())
    days, seconds = divmod(seconds, 86400)
    span = f'{days}d{seconds}s'
    response = api.fulcra_v1_records(f'{{__name__="{channel}"}}[{span}] @ {anchor}', fulcra_userid=owner)
    rows = [json.loads(line) for line in response.splitlines() if line.strip()]
    # Keep undated rows for emptiness checks, but never as matching evidence.
    return [row for row in rows if (stamp := timestamp(row.get('start_time'))) is None or start <= stamp < end]


def save(api, own, channel, details, expected):
    entry = c.owned(api, own, channel)
    description = entry.get('description') or ''
    if c.metadata(description) != expected:
        raise ValueError('Connection details changed.')
    span = c.metadata(description, with_span=True)
    rendered = 'Connection details: ' + json.dumps(details, ensure_ascii=True, separators=(',', ':'))
    if span:
        if span[0] and not description[span[0] - 1].isspace():
            rendered = '\n' + rendered
        if span[1] < len(description) and not description[span[1]].isspace():
            rendered += '\n'
    updated = description[:span[0]] + rendered + description[span[1]:] if span else description + '\n' + rendered
    result = c.update(api, channel, description=updated, expected_description=description)
    if not result['verified']:
        raise ValueError('Connection details not verified.')


def share(api, own, channel, peer):
    if api.get_fulcra_userid() != own:
        raise ValueError('Account changed.')
    api.create_datashare(datashare_name='connect-our-agents invitation response',
        fulcra_data_types=[channel], allowed_user_ids=[peer], allowed_group_ids=[],
        share_all_data=False, time_start=None, time_end=None)
    if c.audience(api, own, channel) != {peer} or api.get_fulcra_userid() != own:
        raise ValueError('Return share not verified.')


def accept(api, inviter_userid, topic, sender, introduction, response_channel=None):
    result = dict(connected=False, retryable=False, next_step=c.RECOVERY)
    attempted = False
    with LOCK:
        try:
            own = api.get_fulcra_userid()
            if not c.exact(own) or not c.exact(inviter_userid) or own == inviter_userid:
                raise ValueError('Distinct exact owner and inviter required.')
            if not isinstance(topic, str) or not re.fullmatch(r'(handshake|open_invitation) [0-9a-f]{32}', topic):
                raise ValueError('Exact invitation topic required.')
            mid = str(uuid4())
            record = c.connections.build_message(sender=sender, body=introduction, record_id=mid,
                                                  topic=topic, priority='P2')
            result.update(own_userid=own, mid=mid)
            catalog = api.v1_catalog(fulcra_userid=own)
            for entry in catalog:
                if entry.get('fulcra_userid') != own or entry.get('api_version') != 'v1':
                    continue
                prior = c.metadata(entry.get('description')).get('acceptance', {})
                if prior.get('inviter_userid') == inviter_userid and prior.get('topic') == topic:
                    return {**result, 'status': 'recovery_required', 'data_type': entry['id'], 'mid': prior['mid']}
            marker = dict(inviter_userid=inviter_userid, topic=topic, mid=mid)
            if response_channel is not None:
                if not c.exact(response_channel, c.CHANNEL_PATTERN):
                    raise ValueError('Exact response channel required.')
                entry = c.owned(api, own, response_channel)
                if history(api, own, response_channel, entry) or targeted(api, response_channel):
                    raise ValueError('Response channel must be empty and unshared.')
                expected = c.metadata(entry.get('description'))
                if expected.get('invitation') or expected.get('acceptance'):
                    raise ValueError('Channel already reserved.')
                if api.validate_records(response_channel, [record], 'v1'):
                    raise ValueError('Incompatible response channel.')
                details = {**expected, 'version': 1, 'acceptance': marker}
                attempted = True
                save(api, own, response_channel, details, expected)
            else:
                details = dict(version=1, acceptance=marker)
                attempted = True
                created = api.create_data_type('Event', dict(name='Agent invitation response',
                    description='Agent contact channel\nConnection details: ' + json.dumps(details),
                    record_spec={'schema': json.dumps(c.connections.CHANNEL_FIELDS)}))
                response_channel = created['id']
            result['data_type'] = response_channel
            if not c.exact(response_channel, c.CHANNEL_PATTERN):
                raise ValueError('Invalid created channel.')
            entry = c.owned(api, own, response_channel)
            if c.metadata(entry.get('description')).get('acceptance') != marker or api.validate_records(response_channel, [record], 'v1'):
                raise ValueError('Reservation or channel schema not verified.')
            share(api, own, response_channel, inviter_userid)
            result['shared'] = True
            outcome = c.send(api, response_channel, sender, introduction, topic=topic, record_id=mid,
                             target_peer_userid=inviter_userid)
            return {**result, 'status': 'introduction_posted' if outcome['status'] == 'posted' else outcome['status'],
                    'sent': outcome['status'] == 'posted', 'send_result': outcome}
        except Exception:
            return {**result, 'status': 'uncertain' if attempted else 'rejected', 'reason': 'Acceptance not verified.'}


def targeted(api, channel):
    return [s for s in api.get_datashares()
            if not s.get('share_all_data') and s.get('fulcra_data_types') == [channel]]


def evidence(api, own, prefix='handshake'):
    found = {}
    channels = set()
    for grant in api.get_shared_datasets():
        types = grant.get('fulcra_data_types') or []
        peer = grant.get('sharing_fulcra_userid')
        if (grant.get('grant_type') == 'user' and c.exact(peer) and peer != own
                and len(types) == 1 and c.exact(types[0], c.CHANNEL_PATTERN)
                and not any(grant.get(k) for k in ('share_all_data', 'group_id', 'time_start', 'time_end', 'file_paths', 'files'))):
            channels.add((peer, types[0]))
    for peer, channel in sorted(channels):
        resolved = api.resolve_data_type(channel, fulcra_userid=peer)
        if (len(resolved) != 1 or resolved[0].get('id') != channel
                or resolved[0].get('fulcra_userid') != peer or resolved[0].get('api_version') != 'v1'
                or resolved[0].get('deprecated') or resolved[0].get('deleted_at')):
            raise ValueError('Incoming channel not verified.')
        entry = resolved[0]
        if not c.compatible(api, peer, channel):
            continue
        if (c.metadata(entry.get('description')).get('invitation', {}).get('prefix') == 'open_invitation'
                or entry.get('name') == 'connect-our-agents-standing-invitation'):
            continue
        for row in history(api, peer, channel, entry):
            topic = row.get('topic', '')
            if (timestamp(row.get('start_time')) is None or row.get('kind') != 'message'
                    or not isinstance(topic, str) or not re.fullmatch(prefix + r' [0-9a-f]{32}', topic)):
                continue
            pairs = found.setdefault(topic.split(' ')[1], [])
            if (peer, channel) not in pairs:
                pairs.append((peer, channel))
    return found


def verify_evidence(api, own, channel, details, pair, prefix='handshake'):
    current = c.metadata(c.owned(api, own, channel).get('description'))
    invite = details['invitation']
    rows = evidence(api, own, prefix).get(invite['code'], [])
    if prefix == 'open_invitation':
        rows = [r for r in rows if r[0] == pair[0]]
    if current != details or rows != [pair]:
        raise ValueError('Invitation evidence changed.')


def add_peer(details, peer, incoming):
    pair = dict(fulcra_userid=peer, data_type=incoming)
    if pair not in details.setdefault('peers', []):
        details['peers'].append(pair)


def match_open(api, own, entry, original):
    template = entry['id']
    details = copy.deepcopy(original)
    invite = details['invitation']
    results = []
    rows = evidence(api, own, 'open_invitation').get(invite['code'], [])
    for peer, incoming in rows:
        binding = invite['responses'].get(peer)
        if binding and binding['state'] == 'completed':
            continue
        item = dict(template_data_type=template, peer_userid=peer, incoming_data_type=incoming,
                    status='uncertain', retryable=False)
        results.append(item)
        def verify():
            verify_evidence(api, own, template, details, (peer, incoming), 'open_invitation')
            if targeted(api, template):
                raise ValueError('Template must not have targeted grants.')
        def persist():
            nonlocal original
            save(api, own, template, details, original)
            original = copy.deepcopy(details)
        try:
            verify()
            if binding and binding['incoming_data_type'] != incoming:
                raise ValueError('Responder already bound.')
            if not binding:
                # Reserve before creation; an uncertain create is never repeated.
                binding = dict(state='creating', incoming_data_type=incoming, identifier='Agent connection')
                invite['responses'][peer] = binding
                persist()
                verify()
                created = api.create_data_type('Event', dict(name='Agent connection',
                    description='Agent contact channel\nContact label: "Agent connection"',
                    record_spec={'schema': json.dumps(c.connections.CHANNEL_FIELDS)}))
                channel = created['id']
                if not c.exact(channel, c.CHANNEL_PATTERN) or channel == template:
                    raise ValueError('New individual channel required.')
                c.owned(api, own, channel)
                if targeted(api, channel) or not c.compatible(api, own, channel):
                    raise ValueError('New unshared contact required.')
                verify()
                binding.update(state='prepared', data_type=channel)
                persist()
            if binding['state'] == 'creating':
                raise ValueError('Prior creation not verified; no retry.')
            channel = binding['data_type']
            item['data_type'] = channel
            c.owned(api, own, channel)
            covering = targeted(api, channel)
            if covering and c.audience(api, own, channel) != {peer}:
                raise ValueError('Audience differs.')
            if not covering and binding['state'] == 'consumed':
                raise ValueError('Prior grant not verified; no retry.')
            if binding['state'] == 'prepared':
                verify()
                binding['state'] = 'consumed'
                persist()
                verify()
                if not targeted(api, channel):
                    share(api, own, channel, peer)
            if c.audience(api, own, channel) != {peer}:
                raise ValueError('Grant not verified.')
            verify()
            source = c.metadata(c.owned(api, own, channel).get('description'))
            paired = copy.deepcopy(source)
            paired['version'] = 1
            add_peer(paired, peer, incoming)
            if paired != source:
                save(api, own, channel, paired, source)
            verify()
            binding['state'] = 'completed'
            persist()
            verify()
            item['status'] = 'matched'
        except Exception:
            item['next_step'] = c.RECOVERY
    return results


def match(api):
    results = []
    with LOCK:
        try:
            own = api.get_fulcra_userid()
            if not c.exact(own):
                raise ValueError('Exact owner required.')
            entries = [e for e in api.v1_catalog(fulcra_userid=own)
                       if e.get('fulcra_userid') == own and e.get('api_version') == 'v1'
                       and c.exact(e.get('id'), c.CHANNEL_PATTERN) and not e.get('deprecated') and not e.get('deleted_at')]
            found = None
            codes = [c.metadata(e.get('description')).get('invitation', {}).get('code') for e in entries]
            for entry in entries:
                original = c.metadata(entry.get('description'))
                invite = original.get('invitation', {})
                code = invite.get('code')
                if (invite.get('state') not in ('prepared', 'consumed')
                        or not isinstance(code, str) or not re.fullmatch('[0-9a-f]{32}', code)
                        or codes.count(code) != 1):
                    continue
                if not c.compatible(api, own, entry['id']):
                    raise ValueError('Compatible invitation channel required.')
                if invite.get('prefix') == 'open_invitation':
                    results.extend(match_open(api, own, entry, original))
                    continue
                if found is None:
                    found = evidence(api, own)
                pairs = found.get(code, [])
                if len(pairs) != 1 and invite['state'] == 'prepared':
                    continue
                channel = entry['id']
                item = dict(data_type=channel, status='uncertain', retryable=False)
                results.append(item)
                if len(pairs) != 1:
                    item['next_step'] = c.RECOVERY
                    continue
                peer, incoming = pairs[0]
                item.update(peer_userid=peer, incoming_data_type=incoming)
                if invite['state'] == 'consumed' and (peer, incoming) != (invite['peer_userid'], invite['incoming_data_type']):
                    raise ValueError('Invitation already bound to another source.')
                covering = targeted(api, channel)
                if covering and c.audience(api, own, channel) != {peer}:
                    raise ValueError('Prepared audience differs from responder.')
                if not covering and invite['state'] == 'consumed':
                    item['next_step'] = c.RECOVERY
                    continue
                details = copy.deepcopy(original)
                if invite['state'] == 'prepared':
                    verify_evidence(api, own, channel, details, (peer, incoming))
                    details['invitation'].update(state='consumed', peer_userid=peer, incoming_data_type=incoming)
                    save(api, own, channel, details, original)
                    verify_evidence(api, own, channel, details, (peer, incoming))
                    if not targeted(api, channel):
                        share(api, own, channel, peer)
                if c.audience(api, own, channel) != {peer}:
                    raise ValueError('Return share not verified.')
                verify_evidence(api, own, channel, details, (peer, incoming))
                consumed = copy.deepcopy(details)
                details['invitation']['state'] = 'completed'
                add_peer(details, peer, incoming)
                save(api, own, channel, details, consumed)
                verify_evidence(api, own, channel, details, (peer, incoming))
                item['status'] = 'matched'
            return {'results': results}
        except Exception:
            return dict(results=results, status='uncertain' if results else 'unavailable', next_step=c.RECOVERY)
