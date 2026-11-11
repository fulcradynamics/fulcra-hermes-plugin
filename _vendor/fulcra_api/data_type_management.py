# Extracted from fulcra_api 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
import json
V1_BASE_TYPES = ('Event', 'Metric')

def is_v1_base_type(name: str) -> bool:
    return name in V1_BASE_TYPES

def create_data_type(source, data_type: dict, name: str, *, description: str | None=None, unit: str | None=None, aggregation: str | None=None, scale: dict | None=None, value_map: dict | None=None, fields_schema: dict | str | None=None, tags: list[str] | None=None, raw_value: str | None=None, scale_labels: list[str] | None=None) -> dict:
    api_version = data_type.get('api_version')
    base_type = data_type['id']
    if api_version == 'v1':
        return _create_v1_data_type(source, base_type, name, description=description, unit=unit, aggregation=aggregation, scale=scale, value_map=value_map, fields_schema=fields_schema, tags=tags, raw_value=raw_value, scale_labels=scale_labels)
    if api_version == 'v1alpha1':
        return _create_v1alpha1_annotation(source, data_type, name, description=description, unit=unit, aggregation=aggregation, scale=scale, value_map=value_map, fields_schema=fields_schema, tags=tags, raw_value=raw_value, scale_labels=scale_labels)
    raise ValueError(f"Cannot create a data type from base type '{base_type}'.")

def _create_v1_data_type(source, base_type: str, name: str, *, description: str | None, unit: str | None, aggregation: str | None, scale: dict | None, value_map: dict | None, fields_schema: dict | str | None, tags: list[str] | None, raw_value: str | None, scale_labels: list[str] | None) -> dict:
    if not is_v1_base_type(base_type):
        raise ValueError(f"'{base_type}' is not a v1 base type; expected Event or Metric.")
    annotation_only = {'tags': tags, 'value': raw_value, 'scale labels': scale_labels}
    used = [opt for opt, val in annotation_only.items() if val]
    if used:
        raise ValueError(f"{', '.join(used)} cannot be used with v1 data type {base_type}.")
    if description is None or not description.strip():
        raise ValueError('A description is required (use -d/--description).')
    metric_only = {'unit': unit, 'aggregation': aggregation, 'scale': scale, 'value_map': value_map}
    if base_type != 'Metric':
        used = [opt for opt, val in metric_only.items() if val is not None]
        if used:
            raise ValueError(f"{', '.join(used)} may only be set for the Metric base type.")
    record_spec: dict = {}
    if unit is not None:
        record_spec['unit'] = unit
    if aggregation is not None:
        record_spec['aggregation'] = aggregation
    if scale is not None:
        record_spec['scale'] = scale
    if value_map is not None:
        record_spec['value_map'] = value_map
    if fields_schema is not None:
        record_spec['schema'] = _schema_json(fields_schema)
    body: dict = {'name': name}
    if description is not None:
        body['description'] = description
    if record_spec:
        body['record_spec'] = record_spec
    return source.create_data_type(base_type, body)

def _create_v1alpha1_annotation(source, data_type: dict, name: str, *, description: str | None, unit: str | None, aggregation: str | None, scale: dict | None, value_map: dict | None, fields_schema: dict | str | None, tags: list[str] | None, raw_value: str | None, scale_labels: list[str] | None) -> dict:
    base_type = data_type['id']
    scale_labels = list(scale_labels or [])
    tags = list(tags or [])
    if fields_schema is not None:
        raise ValueError('fields schema is only valid for v1 data types.')
    if scale is not None:
        raise ValueError('scale is only valid for v1 Metric data types.')
    if value_map is not None:
        raise ValueError('value map is only valid for v1 Metric data types.')
    if data_type.get('record_spec', {}).get('type') != 'metric':
        if aggregation is not None:
            raise ValueError(f'aggregation cannot be used with base data type {base_type}.')
        if raw_value is not None:
            raise ValueError(f'value cannot be used with base data type {base_type}.')
        if unit is not None:
            raise ValueError(f'unit cannot be used with base data type {base_type}.')
    if base_type != 'ScaleAnnotation' and scale_labels:
        raise ValueError(f'scale labels cannot be used with base data type {base_type}.')
    value = None
    match base_type:
        case 'MomentAnnotation':
            annotation_type = 'moment'
        case 'DurationAnnotation':
            annotation_type = 'duration'
        case 'BooleanAnnotation':
            annotation_type = 'boolean'
            if unit is not None:
                raise ValueError(f'unit cannot be used with base data type {base_type}.')
            if raw_value is not None:
                value = _parse_bool(raw_value)
        case 'NumericAnnotation':
            annotation_type = 'numeric'
            if raw_value is not None:
                value = _parse_float(raw_value)
        case 'ScaleAnnotation':
            annotation_type = 'scale'
            if len(scale_labels) != 5:
                raise ValueError(f'scale labels must be exactly 5 values with base data type {base_type}.')
            if unit is not None:
                raise ValueError(f'unit cannot be used with base data type {base_type}.')
        case _:
            raise ValueError(f'Unsupported base type: {base_type}')
    return source.create_annotation(annotation_type=annotation_type, name=name, description=description, tags=tags, metric_kind=aggregation, value=value, unit=unit, scale_labels=scale_labels)

def archive_data_type(source, base_type: str, data_type_id: str) -> dict:
    return source.update_data_type(base_type, data_type_id, {'deprecated': True})

def restore_data_type(source, base_type: str, data_type_id: str) -> dict:
    return source.update_data_type(base_type, data_type_id, {'deprecated': False})

def _parse_fields_schema(fields_schema: dict | str) -> dict:
    if isinstance(fields_schema, str):
        try:
            parsed = json.loads(fields_schema)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid JSON for fields schema: {exc}')
    else:
        parsed = fields_schema
    if not isinstance(parsed, dict):
        raise ValueError('Fields schema must be a JSON object.')
    properties = parsed.get('properties')
    if not isinstance(properties, dict) or not properties:
        raise ValueError('Fields schema must define the fields to add under "properties", e.g. {"properties": {"mood": {"type": "string"}}}.')
    return parsed

def _schema_json(fields_schema: dict | str) -> str:
    return json.dumps(_parse_fields_schema(fields_schema))
_TRUE_STRINGS = {'1', 'true', 't', 'yes', 'y', 'on'}
_FALSE_STRINGS = {'0', 'false', 'f', 'no', 'n', 'off'}

def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_STRINGS:
        return True
    if normalized in _FALSE_STRINGS:
        return False
    raise ValueError(f"'{value}' is not a valid boolean value.")

def _parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"'{value}' is not a valid numeric value.")
