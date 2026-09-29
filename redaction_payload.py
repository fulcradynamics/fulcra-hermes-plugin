"""Recognized text payloads only; opaque protocol data is never rewritten."""
from copy import deepcopy
import json
import re
from types import SimpleNamespace as NS


def refusal(reason):
    # A local assistant response in each real transport's wire shape, not a raised
    # middleware exception (Hermes intentionally fails open on those).
    text = 'Local Fulcra privacy refusal: ' + reason
    message = NS(role='assistant', content=text, tool_calls=[], reasoning=None)
    return NS(choices=[NS(index=0, message=message, finish_reason='stop')],
              content=[NS(type='text', text=text)], stop_reason='end_turn',
              output=[NS(type='message', role='assistant', status='completed',
                         content=[NS(type='output_text', text=text)])],
              status='completed', output_text=text,
              usage=NS(prompt_tokens=0, completion_tokens=0, total_tokens=0,
                       input_tokens=0, output_tokens=0))


def json_strings(value, transform):
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [json_strings(v, transform) for v in value]
    if isinstance(value, dict):
        # Property names are schema, not text. Refuse rather than rename them.
        if any(transform(k) != k for k in value):
            raise ValueError('Private JSON key')
        return {k: json_strings(v, transform) for k, v in value.items()}
    if value is None or type(value) in (int, float, bool):
        return value
    raise ValueError('Unknown JSON value')


def redact_request(request, entries):
    mapping = dict(entries)
    tokens = re.compile('|'.join(re.escape(t) for t in mapping.values())) if mapping else None
    pattern = re.compile('|'.join(re.escape(p) for p in [*mapping.values(), *sorted(mapping, key=len, reverse=True)])) if mapping else None
    count = 0

    def validate_placeholders(value):
        # Only this request's allocated tokens are trusted replay. Reject all
        # other reserved text before substitution, including malformed tokens.
        if '{REDACTED-' in (tokens.sub('', value) if tokens else value):
            raise ValueError('Unknown placeholder')

    def text(value):
        nonlocal count
        if not isinstance(value, str):
            raise ValueError('Non-text')
        validate_placeholders(value)
        def replace(match):
            nonlocal count
            if match[0] in mapping:
                count += 1
                return mapping[match[0]]
            return match[0]
        result = pattern.sub(replace, value) if pattern else value
        if any(phrase in result for phrase in mapping):
            raise ValueError('Residual private literal')
        return result

    def opaque(value):
        # Preserve identifiers, signatures, schemas, URLs, etc byte-for-byte. If
        # a literal occurs there, blocking is safer than corrupting the protocol.
        if isinstance(value, str):
            validate_placeholders(value)
            if any(p in value for p in mapping):
                raise ValueError('Private opaque data')
        elif isinstance(value, (dict, list)):
            for part in (list(value.keys()) + list(value.values()) if isinstance(value, dict) else value):
                opaque(part)
        elif value is not None and type(value) not in (int, float, bool):
            raise ValueError('Unknown opaque value')

    def content(value):
        if isinstance(value, str):
            return text(value)
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError('Unknown content')
        for block in value:
            if not isinstance(block, dict):
                raise ValueError('Unknown block')
            kind = block.get('type')
            if kind in ('text', 'input_text', 'output_text') or set(block) == {'text'}:
                block['text'] = text(block['text'])
                opaque({k: v for k, v in block.items() if k != 'text'})
            elif kind == 'tool_result':
                block['content'] = content(block['content'])
                opaque({k: v for k, v in block.items() if k != 'content'})
            elif kind == 'tool_use':
                block['input'] = json_strings(block['input'], text)
                opaque({k: v for k, v in block.items() if k != 'input'})
            elif kind in ('thinking', 'redacted_thinking'):
                raise ValueError('Signed replay unsupported')
            else:
                # Multimodal/unknown blocks aren't silently claimed as protected.
                raise ValueError('Unsupported block')
        return value

    if type(request) is not dict:
        raise ValueError('Unknown request')
    # Restoration and the completed-text notice are not structured-output safe.
    # Reject before next_call even if restoration was switched off.
    for options in (request, request.get('extra_body') or {}):
        for output_format in (options.get('response_format'), (options.get('text') or {}).get('format')):
            if output_format is not None and output_format != {'type': 'text'}:
                raise ValueError('Structured output unsupported')
    allowed = {'messages', 'input', 'system', 'instructions', 'model', 'tools', 'tool_choice',
               'temperature', 'top_p', 'max_tokens', 'max_completion_tokens', 'max_output_tokens',
               'stream', 'stream_options', 'stop', 'seed', 'presence_penalty', 'frequency_penalty',
               'parallel_tool_calls', 'reasoning_effort', 'reasoning', 'thinking', 'text',
               'response_format', 'service_tier', 'store', 'metadata', 'prompt_cache_key',
               'prompt_cache_retention', 'include', 'extra_headers', 'extra_body', 'timeout',
               'inferenceConfig', 'toolConfig', 'modelId', 'additionalModelRequestFields',
               '__bedrock_converse__', '__bedrock_region__'}
    if set(request) - allowed or ('messages' in request and 'input' in request):
        raise ValueError('Unsupported request fields')
    # SDK body overlays can replace validated messages after this boundary.
    # Refuse extensions rather than scanning JSON-encoded overrides as opaque text.
    if request.get('extra_body'):
        raise ValueError('SDK body overlays unsupported')
    result = deepcopy(request)
    key = 'input' if 'input' in result else 'messages'
    messages = result[key]
    if not isinstance(messages, list) or not messages:
        raise ValueError('Missing messages')
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError('Unknown message')
        if set(message) - {'role', 'content', 'tool_calls', 'name', 'tool_call_id', 'reasoning',
                           'reasoning_content', 'type', 'id', 'call_id', 'arguments', 'output',
                           'status', 'phase'}:
            raise ValueError('Unknown message fields')

        before = count
        kind = message.get('type', 'message')
        if kind == 'function_call':
            message['arguments'] = json.dumps(json_strings(json.loads(message['arguments']), text), ensure_ascii=False)
            handled = {'arguments'}
        elif kind == 'function_call_output':
            message['output'] = content(message['output'])
            handled = {'output'}
        elif kind == 'reasoning':
            raise ValueError('Opaque reasoning replay unsupported')
        elif kind == 'message' and message.get('role') in ('system', 'developer', 'user', 'assistant', 'tool'):
            if message['role'] == 'user' and '{REDACTED-' in json.dumps(message.get('content')):
                raise ValueError('Reserved placeholder in user input')
            message['content'] = content(message.get('content'))
            handled = {'content'}
            if 'tool_calls' in message:
                for call in message['tool_calls']:
                    fn = call['function']
                    fn['arguments'] = json.dumps(json_strings(json.loads(fn['arguments']), text), ensure_ascii=False)
                    opaque({k: v for k, v in fn.items() if k != 'arguments'})
                    opaque({k: v for k, v in call.items() if k != 'function'})
                handled.add('tool_calls')
            for field in ('reasoning', 'reasoning_content'):
                if message.get(field) is not None:
                    message[field] = text(message[field])
                    handled.add(field)
        else:
            raise ValueError('Unsupported message')
        opaque({k: v for k, v in message.items() if k not in handled})
        # Deterministic per-message notice: unchanged rules keep old prefixes stable.
        if count > before:
            notice = f'\n[Fulcra: {count - before} literal substitutions. Keep REDACTED placeholders unchanged.]'
            if pattern:
                notice = pattern.sub(lambda m: mapping.get(m[0], m[0]), notice)
            body = message.get('content')
            if isinstance(body, str):
                message['content'] = body + notice
            elif isinstance(body, list):
                for block in reversed(body):
                    if isinstance(block.get('text'), str):
                        block['text'] += notice
                        break
    for field in ('system', 'instructions'):
        if field in result:
            result[field] = content(result[field])
    opaque({k: v for k, v in result.items() if k not in (key, 'system', 'instructions')})
    # A preserved token can overlap another literal at its boundary; notices can
    # also introduce new adjacent text. Check the completed wire copy, not only
    # individual substitution matches. Any residual literal refuses the call.
    opaque(result)
    return result, count


def restore_response(response, entries, count):
    result = deepcopy(response)
    mapping = {token: phrase for phrase, token in entries}
    pattern = re.compile('|'.join(map(re.escape, mapping))) if mapping else None
    restored = 0

    def text(value):
        nonlocal restored
        if not isinstance(value, str):
            raise ValueError('Unknown response text')
        def replace(match):
            nonlocal restored
            restored += 1
            return mapping[match[0]]
        return pattern.sub(replace, value) if pattern else value

    def get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    def put(obj, key, value):
        if isinstance(obj, dict):
            obj[key] = value
        else:
            setattr(obj, key, value)

    # Tool arguments deliberately stay placeholders. No raw secret is handed to
    # a tool by restoration; the human can explicitly turn protection off.
    targets = []
    if getattr(result, 'choices', None):
        for choice in result.choices:
            msg = choice.message
            if getattr(msg, 'reasoning_details', None):
                raise ValueError('Signed response unsupported')
            if msg.content is None:
                msg.content = ''
            targets.append((msg, 'content'))
    elif getattr(result, 'output', None):
        for item in result.output:
            if get(item, 'type') not in ('message', 'function_call'):
                raise ValueError('Unsupported response item')
            if get(item, 'type') == 'message':
                for block in get(item, 'content', []):
                    if get(block, 'type') != 'output_text':
                        raise ValueError('Unsupported response block')
                    targets.append((block, 'text'))
    elif isinstance(getattr(result, 'content', None), list):
        if any(get(b, 'type') not in ('text', 'tool_use') for b in result.content):
            raise ValueError('Unsupported response block')
        targets.extend((b, 'text') for b in result.content if get(b, 'type') == 'text')
        if not targets:
            block = NS(type='text', text='')
            result.content.append(block)
            targets.append((block, 'text'))
    elif isinstance(result, dict) and 'output' in result:
        blocks = result['output']['message']['content']
        if any(set(b) not in ({'text'}, {'toolUse'}) for b in blocks):
            raise ValueError('Unsupported response block')
        targets.extend((b, 'text') for b in blocks if 'text' in b)
        if not targets:
            block = {'text': ''}
            blocks.append(block)
            targets.append((block, 'text'))
    else:
        raise ValueError('Unsupported response')
    if not targets and getattr(result, 'output', None):
        block = NS(type='output_text', text='')
        result.output.append(NS(type='message', role='assistant', status='completed', content=[block]))
        targets.append((block, 'text'))
    for obj, field in targets:
        put(obj, field, text(get(obj, field)))
    notice = f'\n[Fulcra: {count} substitutions outbound; {restored} restored in completed text. Tool arguments remain redacted.]'
    if targets:
        obj, field = targets[-1]
        put(obj, field, get(obj, field) + notice)
    else:
        raise ValueError('No completed text to report')
    return result
