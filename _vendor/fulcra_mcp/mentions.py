# Extracted from fulcra_mcp 74f5041fbb012991e291697954c38e83901c7a04; see PROVENANCE.md.
import json
from importlib.resources import files
CHANNEL_SCHEMA = json.loads(files(__package__).joinpath('static/connection-schema.json').read_text())

def _semantic(value, key=None):
    if isinstance(value, list):
        return sorted(value) if key in ('enum', 'required', 'required_fields') else [_semantic(v) for v in value]
    if isinstance(value, dict):
        return {k: _semantic(v, k) for k, v in value.items() if k not in ('description', 'title', 'default')}
    return value

def _compatible_schema(entry):
    return _semantic({'fields': {k: entry.get('fields', {}).get(k) for k in CHANNEL_SCHEMA['fields']}, 'required_fields': entry.get('required_fields')}) == _semantic(CHANNEL_SCHEMA)
