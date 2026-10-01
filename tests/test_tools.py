"""Schema and tool boundary tests without network access."""
import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_tools():
    name = 'tool_fixture_plugin'
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT)]
        sys.modules[name] = package
    return importlib.import_module(name + '.tools')


class ToolTests(unittest.TestCase):
    def test_safety_guards_before_any_request(self):
        tools = load_tools()
        bad = {
            'fulcra_create_share': [{'name': 'x', 'user_ids': []}, {'name': 'x', 'share_all': True}],
            'fulcra_get_records': [{'data_type': 'HeartRate'}, {'data_type': 'HeartRate', 'start_time': '2026-01-01', 'end_time': '2026-01-02'}],
        }
        with patch.object(tools, 'client') as factory:
            for name, cases in bad.items():
                for args in cases:
                    self.assertTrue(getattr(tools, name)(args).startswith('Error:'), (name, args))
            factory.assert_not_called()

    def test_api_validates_arguments_without_custom_error_parsing(self):
        import io
        from email.message import Message
        from urllib.error import HTTPError

        tools = load_tools()
        error = HTTPError('https://private.invalid', 422, 'private', Message(), io.BytesIO(b'{}'))
        with patch.object(error, 'read', wraps=error.read) as read, patch.object(tools, 'client') as factory:
            factory.return_value.v1_catalog.side_effect = error
            result = tools.fulcra_data_catalog({'user_id': 'not-a-uuid'})
            factory.return_value.v1_catalog.assert_called_once_with(fulcra_userid='not-a-uuid')
            read.assert_not_called()
        self.assertIn('HTTP 422', result)
        self.assertNotIn('private', result)

    def test_auth_errors_never_persist_or_include_secrets(self):
        tools = load_tools()
        with patch.object(tools, 'auth_finish', side_effect=ValueError('private-code secret-token')):
            text = tools.fulcra_auth_device({'device_code': 'private-code'})
        self.assertNotIn('private-code', text)
        self.assertNotIn('secret-token', text)
        with patch.object(tools, 'auth_start', return_value='private-code ' * 5000), patch.object(tools, '_bounded_output') as bounded:
            self.assertIn('not persisted', tools.fulcra_auth({}))
            bounded.assert_not_called()
