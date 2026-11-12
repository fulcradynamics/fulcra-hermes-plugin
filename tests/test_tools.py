"""Tool boundaries: argument checks, error text and request routing, offline."""
import importlib
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from plugin import load

ID = '00000000-0000-4000-8000-000000000001'


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tools = load().tools

    def test_argument_checks_run_before_any_request(self):
        bad = {
            'fulcra_create_share': [{'name': 'x', 'user_ids': []}, {'name': 'x', 'user_ids': [ID], 'share_all': True, 'files': ['/a']}],
            'fulcra_get_records': [{'data_type': 'Steps'}, {'data_type': 'Steps', 'latest': True, 'start_time': '2026-01-01T00:00:00Z'},
                                   {'data_type': 'Steps', 'start_time': '2026-01-01', 'end_time': '2026-01-02'}],
            'fulcra_send_agent_message': [{'connection': ID, 'sender': 'a', 'body': 'b', 'reply_to': ID, 'ack': ID}],
            'fulcra_update_data_type': [{'data_type': 'MomentAnnotation/' + ID, 'name': 'x'}],
        }
        with patch.object(self.tools, 'client') as factory:
            for name, cases in bad.items():
                for args in cases:
                    with self.subTest(tool=name, args=args):
                        self.assertTrue(getattr(self.tools, name)(args).startswith('Error:'))
            self.assertFalse(factory.return_value.method_calls)

    def test_errors_withhold_transport_details(self):
        error = HTTPError('https://private.invalid', 422, 'private', Message(), io.BytesIO(b'{}'))
        with patch.object(self.tools, 'client') as factory:
            factory.return_value.v1_catalog.side_effect = error
            self.assertEqual(self.tools.fulcra_data_catalog({}), 'Error: Fulcra HTTP 422; writes may have completed. Verify before retrying.')
            factory.return_value.v1_catalog.side_effect = ValueError('signed-url private-token')
            result = self.tools.fulcra_data_catalog({})
        self.assertIn('outcome uncertain', result)
        self.assertNotIn('private-token', result)
        with patch.object(self.tools, 'auth_finish', side_effect=ValueError('private-code')):
            self.assertNotIn('private-code', self.tools.fulcra_auth_device({'device_code': 'private-code'}))

    def test_signed_out_tools_explain_how_to_sign_in(self):
        client = importlib.import_module('fulcra_plugin.client')
        with tempfile.TemporaryDirectory() as root, \
                patch.object(client, 'credential_path', return_value=Path(root) / 'credentials.json'), \
                patch.object(client.Client, '_open') as request:
            for name, args in (('fulcra_data_catalog', {}), ('fulcra_file_list', {}),
                               ('fulcra_record', {'data_type': 'Steps', 'records': [{}]})):
                result = getattr(self.tools, name)(args)
                self.assertIn('not signed in', result)
                self.assertIn('fulcra_auth_device', result)
            request.assert_not_called()

    def test_delete_share_ends_outgoing_shares_or_leaves_incoming_grants(self):
        with patch.object(self.tools, 'client') as factory:
            api = factory.return_value
            api.get_datashares.return_value = [{'datashare_id': ID}]
            self.assertEqual(json.loads(self.tools.fulcra_delete_share({'share_id': ID})), {'status': 'deleted', 'share_id': ID})
            api.delete_datashare.assert_called_once_with(ID)
            api.get_datashares.return_value = []
            api.get_shared_datasets.return_value = [{'grant_id': ID, 'grant_type': 'group'}]
            self.assertTrue(self.tools.fulcra_delete_share({'share_id': ID}).startswith('Error:'))
            api.get_shared_datasets.return_value = [{'grant_id': ID, 'grant_type': 'user'}]
            self.assertEqual(json.loads(self.tools.fulcra_delete_share({'share_id': ID})), {'status': 'left', 'share_id': ID})
            api.delete_dataset_permission.assert_called_once_with(ID)

    def test_file_and_data_type_removals_report_what_changed(self):
        with patch.object(self.tools, 'client') as factory:
            api = factory.return_value
            api.resolve_filepath.return_value = [{'id': ID}]
            self.assertEqual(json.loads(self.tools.fulcra_file_delete({'path': '/a.txt'})),
                             {'status': 'deleted', 'path': '/a.txt', 'version_id': ID})
            self.assertEqual(json.loads(self.tools.fulcra_data_type_lifecycle({'data_type': 'MomentAnnotation/' + ID, 'action': 'archive'})),
                             {'status': 'archived', 'data_type': 'MomentAnnotation/' + ID})
            api.delete_annotation.assert_called_once_with(ID)

    def test_share_selector_replacement_never_keeps_all_data(self):
        with patch.object(self.tools, 'client') as factory:
            factory.return_value.update_datashare.return_value = {}
            self.tools.fulcra_update_share({'share_id': ID, 'files': ['/private'], 'data_types': []})
            factory.return_value.update_datashare.assert_called_once_with(ID, fulcra_data_types=['file:/private'], share_all_data=False)

    def test_update_data_type_guards_stale_descriptions_and_reads_back(self):
        entry = {'id': 'Event/' + ID, 'fulcra_userid': ID, 'recordable': True, 'description': 'Agent  contact\nchannel'}
        with patch.object(self.tools, 'client') as factory:
            api = factory.return_value
            api.get_fulcra_userid.return_value = ID
            api.v1_catalog.return_value = [entry]
            args = {'data_type': 'Event/' + ID, 'description': 'new', 'expected_description': 'stale'}
            self.assertIn('changed', self.tools.fulcra_update_data_type(args))
            api.update_data_type.assert_not_called()
            args['expected_description'] = 'Agent contact channel'
            self.assertIn('"verified": false', self.tools.fulcra_update_data_type(args))
            api.v1_catalog.side_effect = [[entry], [{**entry, 'description': 'new'}]]
            self.assertIn('"verified": true', self.tools.fulcra_update_data_type(args))


if __name__ == '__main__':
    unittest.main()
