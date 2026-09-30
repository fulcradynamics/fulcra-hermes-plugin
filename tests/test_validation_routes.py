"""Capture real vendored request construction; no API-method mocks or network."""
import base64
import io
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from test_tools import load_tools

ID = '01234567-89ab-cdef-0123-456789abcdef'
TIMES = {'start_time': '2026-01-01T00:00:00+00:00', 'end_time': '2026-01-02T00:00:00+00:00'}
UNSAFE = (ID + '#not-an-id', ID + '?ignored=', '../other', '', '.', '..',
          'x/y', 'x/y/z', 'x\\y', '%2e%2e', 'x%2Fy', 'x%3Fy', 'x%23y')


class RequestSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tools = load_tools()
        from tool_fixture_plugin.client import Client
        from tool_fixture_plugin._vendor.credentials import FulcraCredentials
        claims = base64.urlsafe_b64encode(json.dumps({'fulcradynamics.com/userid': ID}).encode()).decode().rstrip('=')
        self.api = Client(credentials=FulcraCredentials(
            access_token='fixture.' + claims + '.fixture',
            access_token_expiration=datetime.now() + timedelta(hours=1)),
            oidc_audience='https://fixture.invalid/')
        self.requests = []
        self.entry = {'id': 'HeartRate', 'api_version': 'v0', 'fulcra_userid': ID,
                      'recordable': True, 'record_spec': {'type': 'metric'}}
        self.grant = ID
        self.api._open = self.capture
        stub = patch.object(self.tools, 'client', return_value=self.api)
        stub.start()
        self.addCleanup(stub.stop)

    def capture(self, request):
        self.requests.append(request)
        path = urlsplit(request.full_url).path
        if path == '/user/v1/dataset':
            body = [{'grant_id': self.grant, 'grant_type': 'user'}]
        elif path == '/data/v1/catalog':
            body = [self.entry]
        elif path.startswith('/data/v1/catalog/'):
            body = self.entry
        elif path == '/input/v1/file_upload':
            body = {'files': [{'id': ID, 'state': 'uploaded', 'uploaded_at': '2026-01-01'}]}
        elif path.endswith('/download'):
            return io.BytesIO(b'fixture text')
        elif path == '/user/v1alpha1/tag':
            body = [] if request.get_method() == 'GET' else {'id': ID, **json.loads(request.data)}
        else:
            body = {}
        return io.BytesIO(json.dumps(body).encode())

    def call(self, tool, args):
        self.requests.clear()
        return getattr(self.tools, tool)(args)

    def test_route_segments_rejected_before_requests(self):
        for value in UNSAFE:
            self.grant = value
            for tool, args in (
                ('fulcra_delete_share', {'share_id': value}),
                ('fulcra_update_share', {'share_id': value, 'name': 'x'}),
                ('fulcra_leave_share', {'grant_id': value}),
                ('fulcra_shared_data_types', {'user_id': value, **TIMES}),
                ('fulcra_file_restore', {'version_id': value}),
            ):
                with self.subTest(tool=tool, value=value):
                    result = self.call(tool, args)
                    self.assertEqual(self.requests, [])
                    self.assertIn('route segment', result)

    def test_catalog_route_segments_rejected(self):
        for field in ('data_type', 'api_version'):
            for value in UNSAFE:
                args = {'data_type': 'HeartRate', 'api_version': 'v1', 'user_id': ID, field: value}
                # data_type alone permits the documented BaseAnnotation/ID pair.
                if field == 'data_type' and value == 'x/y':
                    continue
                with self.subTest(field=field, value=value):
                    result = self.call('fulcra_data_type_schema', args)
                    self.assertEqual(self.requests, [])
                    self.assertIn('route segment', result)
        for tool, extra in (('fulcra_get_records', TIMES), ('fulcra_record', {'records': []}),
                            ('fulcra_delete_records', {'record_ids': [ID]})):
            args = {'data_type': 'HeartRate', 'api_version': 'v1?x=', **extra}
            if tool == 'fulcra_get_records':
                args['user_id'] = ID
            with self.subTest(tool=tool):
                self.assertIn('route segment', self.call(tool, args))
                self.assertEqual(self.requests, [])

    def test_v0_group_route_segments_rejected_after_catalog(self):
        for field in ('group_id', 'participant_id'):
            for value in UNSAFE:
                with self.subTest(field=field, value=value):
                    result = self.call('fulcra_get_records', {'data_type': 'HeartRate', **TIMES,
                                       'group_id': ID, 'participant_id': ID, field: value})
                    self.assertIn('route segment', result)
                    self.assertEqual([urlsplit(r.full_url).path for r in self.requests], ['/data/v1/catalog'])

    def test_falsey_explicit_owners_never_fall_back(self):
        for owner in ('', None, False, 0, [], {}):
            for tool, args in (
                ('fulcra_file_list', {}), ('fulcra_file_stat', {'path': '/x'}),
                ('fulcra_file_download', {'path': '/x'}), ('fulcra_data_catalog', {}),
                ('fulcra_data_type_schema', {'data_type': 'HeartRate'}),
                ('fulcra_get_records', {'data_type': 'HeartRate', **TIMES}),
            ):
                with self.subTest(tool=tool, owner=owner):
                    result = self.call(tool, {**args, 'user_id': owner})
                    self.assertEqual(self.requests, [])
                    self.assertIn('owner', result)

    def test_nonlist_annotation_containers_never_write(self):
        for field in ('tags', 'scale_labels'):
            for value in ('abcde', {'a': 1, 'b': 2}, '', {}, None, False, 1):
                with self.subTest(field=field, value=value):
                    result = self.call('fulcra_create_data_type', {
                        'base_type': 'ScaleAnnotation', 'name': 'x', 'tags': ['valid'], field: value})
                    self.assertEqual(self.requests, [])
                    self.assertIn('list', result)

    def test_ordinary_route_spelling_reaches_real_transport(self):
        for value in (ID, 'not-a-uuid!'):
            self.grant = value
            for tool, args, method, path in (
                ('fulcra_delete_share', {'share_id': value}, 'DELETE', '/user/v1/datashare/' + value),
                ('fulcra_update_share', {'share_id': value, 'name': ''}, 'PUT', '/user/v1/datashare/' + value),
                ('fulcra_leave_share', {'grant_id': value}, 'DELETE', '/user/v1/dataset/' + value),
                ('fulcra_shared_data_types', {'user_id': value, **TIMES}, 'GET', '/user/v1/shared/' + value + '/data_types'),
                ('fulcra_file_restore', {'version_id': value}, 'POST', '/input/v1/file_upload/' + value + '/restore'),
            ):
                with self.subTest(tool=tool, value=value):
                    self.assertFalse(self.call(tool, args).startswith('Error:'))
                    self.assertEqual(self.requests[-1].get_method(), method)
                    self.assertEqual(urlsplit(self.requests[-1].full_url).path, path)
        for data_type in ('bad-type!', 'NumericAnnotation/' + ID):
            self.call('fulcra_data_type_schema', {'data_type': data_type, 'api_version': 'bad-version!', 'user_id': ID})
            self.assertEqual(urlsplit(self.requests[0].full_url).path,
                             '/data/v1/catalog/' + data_type + '/bad-version!')
        self.call('fulcra_get_records', {'data_type': 'HeartRate', **TIMES,
                                       'group_id': 'bad-group!', 'participant_id': 'bad-participant!'})
        self.assertEqual(urlsplit(self.requests[-1].full_url).path,
                         '/data/v0/pool/bad-group!/participant/bad-participant!/metric_samples')

    def test_omitted_and_nonempty_file_owners_preserved(self):
        for owner in (None, ID, 'not-a-uuid!'):
            for tool in ('fulcra_file_list', 'fulcra_file_stat', 'fulcra_file_download'):
                with self.subTest(tool=tool, owner=owner):
                    args = {'path': '/x'}
                    if owner is not None:
                        args['user_id'] = owner
                    self.assertFalse(self.call(tool, args).startswith('Error:'))
                    for request in self.requests:
                        query = parse_qs(urlsplit(request.full_url).query)
                        self.assertEqual(query.get('fulcra_userid'), None if owner is None else [owner])

    def test_lists_keep_upstream_transformation_and_api_owned_values(self):
        for tags, labels in (([], []), ([''], ['short']), (['a', 'b'], ['a', 'b', 'c', 'd', 'e'])):
            with self.subTest(tags=tags, labels=labels):
                result = self.call('fulcra_create_data_type', {'base_type': 'ScaleAnnotation',
                                   'name': '', 'tags': tags, 'scale_labels': labels})
                self.assertFalse(result.startswith('Error:'), result)
                tag_posts = [json.loads(r.data) for r in self.requests
                             if r.get_method() == 'POST' and urlsplit(r.full_url).path.endswith('/tag')]
                self.assertEqual(tag_posts, [{'name': t} for t in tags])
                annotation = json.loads(self.requests[-1].data)
                self.assertEqual(annotation['spec']['scale']['label_mapping']['string']['mapping'],
                                 {str(i + 1): label for i, label in enumerate(labels)} if labels else None)

    def test_query_parameters_are_not_treated_as_route_segments(self):
        value = '../not-an-id?#%'
        self.call('fulcra_data_catalog', {'data_type': value, 'user_id': value})
        self.assertEqual(parse_qs(urlsplit(self.requests[0].full_url).query),
                         {'data_type': [value], 'fulcra_userid': [value]})
        self.entry['api_version'] = 'v1alpha1'
        self.call('fulcra_get_records', {'data_type': 'HeartRate', **TIMES,
                                       'group_id': value, 'participant_id': value})
        self.assertEqual(urlsplit(self.requests[-1].full_url).path, '/data/v1alpha1/metric/HeartRate')
        query = parse_qs(urlsplit(self.requests[-1].full_url).query)
        self.assertEqual(query['pool_id'], [value])
        self.assertEqual(query['participant_id'], [value])
