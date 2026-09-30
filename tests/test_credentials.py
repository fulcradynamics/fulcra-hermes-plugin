"""Native wire exercise over local HTTP with synthetic credentials only."""
import base64
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from test_tools import load_tools

ID = '01234567-89ab-cdef-0123-456789abcdef'


class CredentialTests(unittest.TestCase):
    def test_local_http_catalog_record_upload_download_and_refresh(self):
        tools = load_tools()
        native = importlib.import_module('tool_fixture_plugin.client')
        received = []
        payload = b'\xffbinary\r\n'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.respond()
            def do_POST(self):
                self.respond()
            def respond(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                received.append((self.command, self.path, dict(self.headers), body))
                path = urlsplit(self.path).path
                invalid = parse_qs(urlsplit(self.path).query).get('data_type') == ['bad type']
                if invalid:
                    result = {'detail': [{'loc': ['query', 'data_type'], 'type': 'string_pattern_mismatch', 'msg': 'private-value', 'input': 'private-value'}]}
                elif path == '/data/v1/catalog':
                    result = [{'id': 'MomentAnnotation', 'api_version': 'v1alpha1', 'fulcra_userid': ID, 'recordable': True, 'record_spec': {'type': 'event'}}]
                elif path.endswith('/schema'):
                    result = {'type': 'object', 'properties': {'note': {'type': 'string'}}, 'required': ['note']}
                elif path.startswith('/ingest/'):
                    result = {'upload_id': ID}
                elif path == '/input/v1/file_upload' and self.command == 'POST':
                    result = {'id': ID, 'url': f'http://127.0.0.1:{self.server.server_port}/signed'}
                elif path == '/input/v1/file_upload':
                    result = {'files': [{'id': ID}]}
                elif path.endswith('/download'):
                    result = payload
                else:
                    result = {}
                data = result if isinstance(result, bytes) else json.dumps(result).encode()
                self.send_response(422 if invalid else 200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        token = 'header.' + base64.urlsafe_b64encode(json.dumps({'fulcradynamics.com/userid': ID}).encode()).decode() + '.signature'
        with tempfile.TemporaryDirectory() as root, patch.object(native, 'credential_path', return_value=Path(root) / 'credentials.json'):
            creds = native.FulcraCredentials(access_token=token, refresh_token='old-refresh', access_token_expiration=datetime.now() - timedelta(seconds=1))
            native.save_credentials(creds)
            api = native.Client(credentials=creds, oidc_audience=f'http://127.0.0.1:{server.server_port}')
            refreshed = native.FulcraCredentials(access_token=token, access_token_expiration=datetime.now() + timedelta(hours=1))
            with patch.object(api.oidc, 'refresh_credentials', return_value=refreshed) as refresh, patch.object(tools, 'client', return_value=api):
                self.assertEqual(json.loads(tools.fulcra_data_catalog({}))[0]['id'], 'MomentAnnotation')
                error = tools.fulcra_data_catalog({'data_type': 'bad type'})
                self.assertIn('HTTP 422', error)
                self.assertIn('query.data_type: string_pattern_mismatch', error)
                self.assertNotIn('private-value', error)
                self.assertNotIn('http://', error)
                self.assertEqual(parse_qs(urlsplit(received[-1][1]).query)['data_type'], ['bad type'])
                self.assertEqual(json.loads(tools.fulcra_record({'data_type': 'MomentAnnotation', 'records': [{'note': 'literal\né'}]})), {'upload_id': ID})
                self.assertEqual(json.loads(tools.fulcra_file_upload({'path': '/binary', 'content': 'hello'})), {'id': ID})
                self.assertEqual(api.read_file('/binary'), payload)
                refresh.assert_called_once()
            self.assertEqual(native.client().fulcra_credentials.refresh_token, 'old-refresh')
        post = next(r for r in received if r[1].startswith('/ingest/'))
        self.assertEqual(post[3], b'{"note": "literal\\n\\u00e9"}\n')
        self.assertEqual(post[2]['Content-Type'], 'application/x-jsonl')
        signed = next(r for r in received if r[1] == '/signed')
        self.assertNotIn('Authorization', signed[2])
        self.assertEqual(signed[3], b'hello')
        self.assertTrue(all(r[2].get('Authorization') == 'Bearer ' + token for r in received if r[1] != '/signed'))

    def test_cross_origin_redirect_drops_bearer(self):
        import urllib.request
        load_tools()
        native = importlib.import_module('tool_fixture_plugin.client')
        self.assertTrue(hasattr(native, 'PrivateRedirect'), 'redirect privacy adapter missing')
        request = urllib.request.Request('https://api.example/file', headers={'Authorization': 'Bearer private'})
        redirected = native.PrivateRedirect().redirect_request(request, None, 302, 'found', {}, 'https://storage.example/signed')
        self.assertFalse(redirected.has_header('Authorization'))
        same = native.PrivateRedirect().redirect_request(request, None, 302, 'found', {}, 'https://api.example/other')
        self.assertEqual(same.get_header('Authorization'), 'Bearer private')

    def test_os_user_path_not_profile_or_xdg(self):
        load_tools()
        native = importlib.import_module('tool_fixture_plugin.client')
        with patch.dict('os.environ', {'HERMES_HOME': '/profiles/a', 'XDG_CONFIG_HOME': '/different'}):
            self.assertEqual(native.credential_path(), Path.home() / '.config/fulcra/credentials.json')
