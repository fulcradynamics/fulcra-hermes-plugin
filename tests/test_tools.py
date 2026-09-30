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
            'fulcra_delete_records': [{'data_type': 'HeartRate', 'record_ids': []}, {'data_type': 'HeartRate', 'record_ids': ['not-a-uuid']}],
            'fulcra_update_share': [{'share_id': 'bad', 'share_all': 'false'}, {'share_id': 'bad', 'user_ids': None}],
            'fulcra_file_share': [{'name': 'x', 'path': '', 'user_ids': ['owner']}, {'name': 'x', 'path': '/', 'user_ids': []}],
            'fulcra_data_type_lifecycle': [{'data_type': 'NumericAnnotation/01234567-89ab-cdef-0123-456789abcdef', 'action': 'typo'}],
            'fulcra_get_records': [{'data_type': 'HeartRate'}, {'data_type': 'HeartRate', 'start_time': '2026-01-01', 'end_time': '2026-01-02'}],
        }
        with patch.object(tools, 'client') as factory:
            for name, cases in bad.items():
                for args in cases:
                    self.assertTrue(getattr(tools, name)(args).startswith('Error:'), (name, args))
            factory.assert_not_called()

    def test_auth_errors_never_persist_or_include_secrets(self):
        tools = load_tools()
        with patch.object(tools, 'auth_finish', side_effect=ValueError('private-code secret-token')):
            text = tools.fulcra_auth_device({'device_code': 'private-code'})
        self.assertNotIn('private-code', text)
        self.assertNotIn('secret-token', text)
        with patch.object(tools, 'auth_start', return_value='private-code ' * 5000), patch.object(tools, '_bounded_output') as bounded:
            self.assertIn('not persisted', tools.fulcra_auth({}))
            bounded.assert_not_called()
