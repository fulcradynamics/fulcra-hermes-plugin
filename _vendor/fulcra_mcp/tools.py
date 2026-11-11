# Extracted from fulcra_mcp 74f5041fbb012991e291697954c38e83901c7a04; see PROVENANCE.md.
V1_RECORD_FIELDS_SET_BY_TOOL = frozenset({'id', 'sources', 'tags', 'start_time', 'end_time'})
RECORD_PLUMBING_FIELDS = frozenset({'id', 'sources', 'tags'})

def _recordable_fields(properties: dict) -> list[str]:
    return sorted((k for k in properties if k not in RECORD_PLUMBING_FIELDS))

def _schema_type(prop: dict) -> str:
    if isinstance(prop.get('type'), str):
        return prop['type']
    if isinstance(prop.get('type'), list):
        return '|'.join((t for t in prop['type'] if t != 'null')) or 'any'
    types = [option['type'] for option in prop.get('anyOf', []) if isinstance(option, dict) and option.get('type') not in (None, 'null')]
    return '|'.join(types) or 'any'
SCHEMA_NOISE_KEYWORDS = frozenset({'title', 'default'})

def _field_schema(prop: dict) -> str | dict:
    options = [o for o in prop.get('anyOf', []) if isinstance(o, dict)]
    non_null = [o for o in options if o.get('type') != 'null']
    if options and len(non_null) == 1:
        prop = {**{k: v for k, v in prop.items() if k != 'anyOf'}, **non_null[0]}
    if isinstance(prop.get('type'), list):
        prop = {**prop, 'type': _schema_type(prop)}
    schema = {k: v for k, v in prop.items() if k not in SCHEMA_NOISE_KEYWORDS}
    if set(schema) <= {'type'}:
        return _schema_type(prop)
    return schema

def _user_defined_fields(schema: dict) -> tuple[dict[str, str | dict], list[str]]:
    properties = schema.get('properties') if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return ({}, [])
    fields = {name: _field_schema(properties[name]) for name in _recordable_fields(properties) if name not in V1_RECORD_FIELDS_SET_BY_TOOL and isinstance(properties[name], dict)}
    required = schema.get('required')
    required = sorted((f for f in required if f in fields)) if isinstance(required, list) else []
    return (fields, required)
