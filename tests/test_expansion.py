"""Native writes, files and scope boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from test_tools import load_tools

ID = '01234567-89ab-cdef-0123-456789abcdef'
DT = 'NumericAnnotation/' + ID


class NativeOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        self.api = Mock()
        self.api.get_fulcra_userid.return_value = ID
        self.api.resolve_data_type.return_value = [{'id': DT, 'fulcra_userid': ID, 'api_version': 'v1alpha1', 'recordable': True}]
        self.api.validate_records.return_value = []
        self.api.record_data_type.return_value = {'upload_id': ID}
        stub = patch.object(self.tools, 'client', return_value=self.api)
        stub.start()
        self.addCleanup(stub.stop)

    def test_record_validation_annotation_source_and_deletion(self):
        args = {'data_type': DT, 'records': [{'note': 'literal\n--option', 'value': -2}]}
        self.assertEqual(json.loads(self.tools.fulcra_record(args)), {'upload_id': ID})
        rows = self.api.record_data_type.call_args.args[1]
        self.assertEqual(rows, [{**args['records'][0], 'sources': ['com.fulcradynamics.annotation.' + ID]}])
        self.assertNotIn('sources', args['records'][0])
        self.api.resolve_data_type.assert_called_with(DT, None, ID)
        self.api.validate_records.return_value = [(0, 'private invalid payload', None)]
        before = self.api.record_data_type.call_count
        self.assertIn('catalog schema', self.tools.fulcra_record(args))
        self.assertEqual(self.api.record_data_type.call_count, before)
        self.api.validate_records.return_value = []
        self.tools.fulcra_delete_records({'data_type': DT, 'record_ids': [ID]})
        self.api.record_data_type.assert_called_with('DeletedRecord', [{'record_id': ID, 'data_type': 'NumericAnnotation'}], 'v1alpha1')

    def test_shares_explicit_replacements_and_independent_recipients(self):
        self.api.create_datashare.return_value = self.api.update_datashare.return_value = {}
        self.tools.fulcra_create_share({'name': 'scope', 'files': ['/notes/'], 'user_ids': [ID]})
        self.api.create_datashare.assert_called_once_with(datashare_name='scope', fulcra_data_types=['file:/notes/'], allowed_user_ids=[ID], allowed_group_ids=[], share_all_data=False)
        self.tools.fulcra_update_share({'share_id': ID, 'group_ids': [], 'end_time': None})
        self.api.update_datashare.assert_called_once_with(ID, allowed_group_ids=[], time_end=None)
        self.assertIn('both', self.tools.fulcra_update_share({'share_id': ID, 'files': []}))
        self.assertEqual(self.api.update_datashare.call_count, 1)
        self.api.get_shared_datasets.return_value = [{'grant_id': ID, 'grant_type': 'group'}]
        self.assertIn('individual', self.tools.fulcra_leave_share({'grant_id': ID}))
        self.api.delete_dataset_permission.assert_not_called()

    def test_native_files_exact_bytes_and_exclusive_destinations(self):
        self.api.read_file.return_value = b'\xff\x00exact\r\n'
        self.api.write_file.return_value = {'id': ID, 'url': 'private-signed-url'}
        result = self.tools.fulcra_file_upload({'path': '/note', 'content': 'café\r\n'})
        self.assertNotIn('private-signed', result)
        self.api.write_file.assert_called_once_with('/note', 'café\r\n'.encode())
        self.assertIn('local_path', self.tools.fulcra_file_download({'path': '/note'}))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'binary'
            args = {'path': '/note', 'local_path': str(target)}
            self.assertFalse(self.tools.fulcra_file_download(args).startswith('Error'))
            self.assertEqual(target.read_bytes(), self.api.read_file.return_value)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertIn('no overwrites', self.tools.fulcra_file_download(args))
            linked = Path(directory) / 'linked'
            linked.symlink_to(target)
            self.assertIn('no overwrites', self.tools.fulcra_file_download({**args, 'local_path': str(linked)}))

    def test_create_annotation_native_values(self):
        self.api.create_annotation.return_value = {'id': ID}
        self.tools.fulcra_create_data_type({'base_type': 'NumericAnnotation', 'name': '--literal', 'value': -2.5, 'unit': 'points'})
        self.api.create_annotation.assert_called_once_with('numeric', name='--literal', value=-2.5, unit='points', description='', tags=[])
        self.tools.fulcra_create_data_type({'base_type': 'ScaleAnnotation', 'name': 'Mood'})
        self.api.create_annotation.assert_called_with('scale', name='Mood', description='', tags=[])
