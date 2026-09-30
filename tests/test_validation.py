"""API-owned ordinary validation and narrowly scoped plugin safety checks."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from test_tools import load_tools

ID = '01234567-89ab-cdef-0123-456789abcdef'


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        self.api = Mock()
        stub = patch.object(self.tools, 'client', return_value=self.api)
        stub.start()
        self.addCleanup(stub.stop)

    def test_ordinary_invalid_arguments_reach_api(self):
        cases = [
            ('fulcra_data_catalog', {'data_type': 'bad type', 'user_id': 'bad'}, 'v1_catalog', (), {'data_type': 'bad type', 'fulcra_userid': 'bad'}),
            ('fulcra_create_data_type', {'base_type': 'NumericAnnotation', 'name': '', 'value': 'bad', 'metric_kind': 'bad'}, 'create_annotation', ('numeric',), {'name': '', 'value': 'bad', 'metric_kind': 'bad', 'description': '', 'tags': []}),
            ('fulcra_create_data_type', {'base_type': 'ScaleAnnotation', 'name': 'x', 'scale_labels': ['short']}, 'create_annotation', ('scale',), {'name': 'x', 'scale_labels': ['short'], 'description': '', 'tags': []}),
            ('fulcra_data_updates', {'start_time': 'bad', 'end_time': 'earlier', 'user_id': 'bad'}, 'data_updates', ('bad', 'earlier', 'bad'), {}),
            ('fulcra_shared_data_types', {'user_id': 'bad', 'start_time': 'bad', 'end_time': 'bad'}, 'list_shared_data_types', ('bad', 'bad', 'bad'), {}),
            ('fulcra_file_stat', {'path': 'relative', 'user_id': 'bad'}, 'file_stat', ('relative', 'bad'), {}),
            ('fulcra_file_restore', {'version_id': 'bad'}, 'restore_file', ('bad',), {}),
            ('fulcra_update_share', {'share_id': 'bad', 'name': '', 'user_ids': ['bad']}, 'update_datashare', ('bad',), {'datashare_name': '', 'allowed_user_ids': ['bad']}),
            ('fulcra_create_share', {'name': '', 'user_ids': ['bad'], 'files': ['/x'], 'start_time': 'bad'}, 'create_datashare', (), {'datashare_name': '', 'allowed_user_ids': ['bad'], 'allowed_group_ids': [], 'fulcra_data_types': ['file:/x'], 'share_all_data': False, 'time_start': 'bad'}),
        ]
        for tool, args, method, positional, keywords in cases:
            with self.subTest(tool=tool, method=method):
                target = getattr(self.api, method)
                target.reset_mock()
                target.side_effect = HTTPError('https://private.invalid/token', 422, 'private', {}, io.BytesIO(b'{}'))
                self.assertIn('HTTP 422', getattr(self.tools, tool)(args))
                target.assert_called_once_with(*positional, **keywords)

    def test_structured_validation_feedback_does_not_echo_private_values(self):
        body = {'detail': [
            {'loc': ['body', 'name'], 'type': 'string_too_short', 'msg': 'private-token', 'input': 'private-token', 'ctx': {'secret': 'private-token'}},
            {'loc': ['body', 'private-token', 2], 'type': 'private-token', 'msg': 'private-token'},
        ]}
        self.api.v1_catalog.side_effect = HTTPError('https://private-token', 422, 'private-token', {}, io.BytesIO(json.dumps(body).encode()))
        result = self.tools.fulcra_data_catalog({})
        self.assertIn('body.name', result)
        self.assertIn('string_too_short', result)
        self.assertNotIn('private-token', result)
        for body in (b'private-token', b'{"detail":"private-token"}', b'{}' * 40000):
            self.api.v1_catalog.side_effect = HTTPError('https://private-token', 400, 'private-token', {}, io.BytesIO(body))
            result = self.tools.fulcra_data_catalog({})
            self.assertIn('HTTP 400', result)
            self.assertNotIn('private-token', result)

    def test_invalid_records_blocked_by_real_upstream_validator(self):
        from tool_fixture_plugin._vendor.core import FulcraAPI
        self.api.resolve_data_type.return_value = [{'id': 'HeartRate', 'api_version': 'v1', 'recordable': True}]
        upstream = FulcraAPI()
        upstream.v1_catalog_schema = Mock(return_value={'type': 'object', 'properties': {'value': {'type': 'number'}}, 'required': ['value']})
        self.api.validate_records.side_effect = upstream.validate_records
        result = self.tools.fulcra_record({'data_type': 'HeartRate', 'records': [{'value': 'private-bad-number'}]})
        self.assertIn('catalog schema', result)
        self.assertNotIn('private-bad-number', result)
        self.api.validate_records.assert_called_once()
        self.api.record_data_type.assert_not_called()

    def test_invalid_actions_never_select_mutation(self):
        for action in ('typo', '', None, False):
            result = self.tools.fulcra_data_type_lifecycle({'data_type': 'NumericAnnotation/' + ID, 'action': action})
            self.assertTrue(result.startswith('Error:'), result)
        self.api.delete_annotation.assert_not_called()
        self.api.restore_annotation.assert_not_called()
        self.api.restore_annotation.return_value = {}
        self.tools.fulcra_data_type_lifecycle({'data_type': 'NumericAnnotation/' + ID, 'action': 'restore'})
        self.api.restore_annotation.assert_called_once_with(ID)

    def test_scope_guards_do_not_depend_on_tool_schema(self):
        bad = [
            ('fulcra_create_share', {'name': 'x', 'user_ids': [ID], 'share_all': 'false'}),
            ('fulcra_create_share', {'name': 'x', 'user_ids': ID, 'share_all': True}),
            ('fulcra_create_share', {'name': 'x', 'user_ids': [ID], 'files': ['']}),
            ('fulcra_update_share', {'share_id': ID, 'user_ids': None}),
            ('fulcra_update_share', {'share_id': ID, 'files': [], 'data_types': [], 'share_all': True}),
            ('fulcra_update_share', {'share_id': ID, 'data_types': ['file:/'], 'files': []}),
            ('fulcra_file_share', {'name': 'x', 'path': '', 'user_ids': [ID]}),
            ('fulcra_delete_records', {'data_type': 'HeartRate', 'record_ids': []}),
            ('fulcra_delete_records', {'data_type': 'HeartRate', 'record_ids': ID}),
            ('fulcra_get_records', {'data_type': 'HeartRate', 'latest': 'false'}),
            ('fulcra_get_records', {'data_type': 'HeartRate', 'latest': True, 'start_time': 'x'}),
            ('fulcra_get_records', {'data_type': 'HeartRate', 'latest': True, 'group_id': ID}),
            ('fulcra_get_records', {'data_type': 'HeartRate', 'latest': True, 'group_id': ID, 'participant_id': ID, 'user_id': ID}),
        ]
        for tool, args in bad:
            with self.subTest(tool=tool, args=args):
                self.assertTrue(getattr(self.tools, tool)(args).startswith('Error:'))
        self.assertEqual(self.api.mock_calls, [])

    def test_local_download_no_overwrite_even_after_preflight_race(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'new'
            def raced(*args):
                target.write_bytes(b'keep')
                return b'replace'
            self.api.read_file.side_effect = raced
            result = self.tools.fulcra_file_download({'path': '/x', 'local_path': str(target)})
            self.assertTrue(result.startswith('Error:'))
            self.assertEqual(target.read_bytes(), b'keep')
            target.unlink()
            target.symlink_to(Path(directory) / 'missing')
            self.api.read_file.reset_mock()
            self.assertIn('no overwrites', self.tools.fulcra_file_download({'path': '/x', 'local_path': str(target)}))
            self.api.read_file.assert_not_called()

    def test_empty_group_identifiers_do_not_fall_back_to_own_records(self):
        self.api.resolve_data_type.return_value = [{'id': 'HeartRate'}]
        with patch.object(self.tools, 'get_records', return_value=[]) as fetch:
            result = self.tools.fulcra_get_records({'data_type': 'HeartRate', 'latest': True, 'group_id': '', 'participant_id': ''})
        self.assertEqual(result, '[]')
        self.api.group_participant.assert_called_once_with('', '')
        self.assertIs(fetch.call_args.args[0], self.api.group_participant.return_value)
