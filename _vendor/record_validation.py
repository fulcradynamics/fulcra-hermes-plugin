# Extracted from fulcra-api-python 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
"""Record validation helpers for FulcraAPI.validate_records.

Two things jsonschema doesn't check on its own, both of which otherwise cost a
record silently after it's uploaded:

- `date-time` values: jsonschema only checks the format when the optional
  rfc3339-validator package is installed, and RFC 3339 alone doesn't match what
  the ETLs accept. `record_format_checker` checks it the way the ETL for the
  data type's API version parses it.
- Fields a data type doesn't declare: the ETLs keep only a schema's properties
  and drop everything else. `strict_schema` makes those an error, and
  `unknown_fields_message` explains them.
"""
import re
from datetime import datetime
import jsonschema
_DATE_TIME = re.compile('(?P<date>\\d{4}-\\d{2}-\\d{2})(?:[T ](?P<time>\\d{2}:\\d{2})(?::(?P<seconds>\\d{2})(?:\\.(?P<fraction>\\d+))?)?(?P<offset>Z|[+-]\\d{2}(?::?\\d{2})?)?)?')

def check_date_time(value: str, api_version: str) -> None:
    match = _DATE_TIME.fullmatch(value.upper())
    if match is None:
        raise ValueError('expected an ISO 8601 date-time, e.g. 2026-09-01T12:34:56Z')
    offset = match['offset']
    if offset and offset != 'Z':
        digits = offset[1:].replace(':', '')
        if len(digits) == 2:
            if api_version != 'v1':
                raise ValueError(f'the offset {offset} needs minutes for {api_version} data types, e.g. {offset}:00')
            digits += '00'
        offset = f'{offset[0]}{digits[:2]}:{digits[2:]}'
    if match['time'] and int(match['time'][:2]) > 23:
        raise ValueError('not a real date-time: hour must be in 0..23')
    normalized = match['date']
    if match['time']:
        normalized += f"T{match['time']}:{match['seconds'] or '00'}"
        if match['fraction']:
            normalized += '.' + match['fraction'][:6]
        if offset:
            normalized += '+00:00' if offset == 'Z' else offset
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f'not a real date-time: {exc}') from None

def record_format_checker(api_version: str) -> jsonschema.FormatChecker:
    checker = jsonschema.FormatChecker()

    @checker.checks('date-time', raises=ValueError)
    def _date_time(value) -> bool:
        if isinstance(value, str):
            check_date_time(value, api_version)
        return True
    return checker
_COMPOSED_KEYWORDS = ('allOf', 'anyOf', 'oneOf', '$ref', 'patternProperties')

def strict_schema(schema: dict) -> dict:
    if not isinstance(schema.get('properties'), dict) or 'additionalProperties' in schema or any((keyword in schema for keyword in _COMPOSED_KEYWORDS)):
        return schema
    return {**schema, 'additionalProperties': False}

def is_unknown_fields_error(error: jsonschema.ValidationError) -> bool:
    return error.validator == 'additionalProperties' and (not error.path)

def _declared_fields(error: jsonschema.ValidationError) -> dict:
    schema = error.schema if isinstance(error.schema, dict) else {}
    declared = schema.get('properties')
    return declared if isinstance(declared, dict) else {}

def unknown_fields(error: jsonschema.ValidationError) -> list[str]:
    declared = _declared_fields(error)
    instance = error.instance if isinstance(error.instance, dict) else {}
    return sorted((k for k in instance if k not in declared))

def unknown_fields_message(error: jsonschema.ValidationError) -> str:
    fields = unknown_fields(error)
    declared = ', '.join(sorted(_declared_fields(error)))
    names = ', '.join((repr(f) for f in fields))
    noun = 'field' if len(fields) == 1 else 'fields'
    return f"{noun} {names} {('is' if len(fields) == 1 else 'are')} not part of this data type and would be dropped; its fields are: {declared}"
