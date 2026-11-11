"""Load the plugin offline with a fake Hermes context and synthetic Fulcra accounts."""
import copy
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_FIELDS = json.loads((ROOT / 'skills/connect-our-agents/references/channel-fields.json').read_text())


def load():
    if 'fulcra_plugin' not in sys.modules:
        spec = importlib.util.spec_from_file_location('fulcra_plugin', ROOT / '__init__.py',
                                                      submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules['fulcra_plugin'] = module
        spec.loader.exec_module(module)
    return sys.modules['fulcra_plugin']


class State:
    def __init__(self):
        self.values, self.path = {}, Path('/profile/plugin-state')

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def set(self, key, value):
        self.values[key] = copy.deepcopy(value)


class Context:
    def __init__(self):
        self.config, self.state = {}, State()
        self.tools, self.hooks, self.commands, self.skills = {}, {}, {}, {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = handler

    def register_hook(self, name, handler):
        self.hooks[name] = handler

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler

    def register_cli_command(self, name, **kwargs):
        self.commands['cli ' + name] = kwargs

    def register_skill(self, name, path):
        self.skills[name] = path


def now():
    return datetime.now(timezone.utc)


class Account:
    """One Fulcra account in a shared synthetic backend, at the FulcraAPI method level."""

    def __init__(self, owner, accounts):
        self.owner, self.accounts = owner, accounts
        self.catalog, self.shares, self.rows, self.files = [], [], {}, []
        accounts[owner] = self

    def get_fulcra_userid(self):
        return self.owner

    def get_user_info(self):
        return {'userid': self.owner}

    def v1_catalog(self, data_type=None, category=None, fulcra_userid=None):
        entries = self.accounts[fulcra_userid or self.owner].catalog
        return copy.deepcopy([e for e in entries if data_type in (None, e['id'])])

    def resolve_data_type(self, data_type, api_version=None, fulcra_userid=None):
        if data_type in ('Event', 'Metric'):
            return [{'id': data_type, 'api_version': 'v1', 'fulcra_userid': None}]
        return self.v1_catalog(data_type, fulcra_userid=fulcra_userid)

    def v1_catalog_schema(self, data_type, api_version, fulcra_userid=None):
        entry = self.resolve_data_type(data_type, fulcra_userid=fulcra_userid)[0]
        return {'type': 'object', **json.loads(entry['record_spec'].get('schema', '{}'))}

    def create_data_type(self, base, body):
        entry = dict(id=f'{base}/{uuid4()}', fulcra_userid=self.owner, api_version='v1', recordable=True,
                     **copy.deepcopy(body))
        entry.setdefault('record_spec', {})['type'] = base.lower()
        self.catalog.append(entry)
        return copy.deepcopy(entry)

    def update_data_type(self, base, type_id, body):
        next(e for e in self.catalog if e['id'] == f'{base}/{type_id}').update(body)
        return {}

    def get_datashares(self):
        return copy.deepcopy(self.shares)

    def create_datashare(self, datashare_name, fulcra_data_types, allowed_user_ids=None, share_all_data=False,
                         allowed_group_ids=None, time_start=None, time_end=None):
        share = dict(datashare_id=str(uuid4()), datashare_name=datashare_name, fulcra_data_types=fulcra_data_types,
                     share_all_data=share_all_data, permissions=[{'allowed_fulcra_userid': u} for u in allowed_user_ids or []])
        self.shares.append(share)
        return copy.deepcopy(share)

    def delete_datashare(self, datashare_id):
        self.shares = [s for s in self.shares if s['datashare_id'] != datashare_id]

    def get_shared_datasets(self):
        return [dict(grant_id=s['datashare_id'], grant_type='user', sharing_fulcra_userid=owner,
                     fulcra_data_types=s['fulcra_data_types'], share_all_data=False)
                for owner, account in self.accounts.items() if owner != self.owner for s in account.shares
                if self.owner in [p['allowed_fulcra_userid'] for p in s['permissions']]]

    def read_records(self, owner, data_type, start=None, end=None):
        if owner != self.owner and not any(g['sharing_fulcra_userid'] == owner and data_type in g['fulcra_data_types']
                                           for g in self.get_shared_datasets()):
            raise PermissionError('Not shared')
        rows = self.accounts[owner].rows.get(data_type, [])
        return [copy.deepcopy(r) for r in rows if start is None or start <= datetime.fromisoformat(r['start_time']) <= end]

    def fulcra_v1_records(self, query, fulcra_userid=None):
        rows = self.read_records(fulcra_userid or self.owner, query.split('"')[1])
        return '\n'.join(json.dumps(r) for r in rows)

    def validate_records(self, data_type, rows, api_version):
        schema = self.v1_catalog_schema(data_type, api_version)
        return [(i, e.message, e) for i, row in enumerate(rows)
                for e in jsonschema.Draft202012Validator(schema).iter_errors(row)]

    def record_data_type(self, data_type, rows, api_version):
        stamp = now().isoformat()
        self.rows.setdefault(data_type, []).extend(
            dict(r, start_time=r.get('start_time', stamp), processed=stamp) for r in rows)
        return {'upload_id': str(uuid4())}

    def data_updates(self, start_time, end_time, fulcra_userid=None, include_shared=False):
        counts = {}
        for data_type, rows in self.rows.items():
            processed = [r for r in rows if start_time <= datetime.fromisoformat(r['processed']) < end_time]
            if processed:
                counts[data_type] = len(processed)
        changes = [f for f in self.files if start_time <= datetime.fromisoformat(f['uploaded_at']) < end_time]
        return {'start_time': start_time.isoformat(), 'end_time': end_time.isoformat(),
                'data_types': counts, 'file_changes': changes}


def accounts(plugin, *owners):
    """Synthetic accounts sharing one backend; returns them and a function to act as one."""
    from unittest.mock import patch
    backend = {}
    made = [Account(owner, backend) for owner in owners]
    current = {'account': made[0]}
    read = lambda api, entry, start=None, end=None, latest=False: api.read_records(entry['fulcra_userid'], entry['id'], start, end)
    patches = [patch.object(plugin.tools, 'client', side_effect=lambda **kwargs: current['account']),
               patch.object(plugin.tools, 'get_records', side_effect=read),
               patch.object(plugin.tools.send.__globals__['records'], 'get_records', side_effect=read),
               patch.object(sys.modules[plugin.tools.send.__module__], 'RETRY_DELAY', 0)]
    for p in patches:
        p.start()

    def act(account):
        current['account'] = account
    return made, act, lambda: [p.stop() for p in patches]
