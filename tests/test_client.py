"""Fulcra API requests go through Hermes's credentialed_provider_request; the plugin never holds a token."""
import importlib
import io
import sys
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from plugin import load


class Response:
    def __init__(self, status=200, body=b'{}', headers=None):
        self.status, self.body, self.headers = status, body, headers or {}


class ClientTests(unittest.TestCase):
    def setUp(self):
        load()
        self.client = importlib.import_module('fulcra_plugin.client')
        self.calls, self.responses = [], []
        module = types.ModuleType('hermes_cli.plugin_provider_requests')

        class ProviderNotSignedIn(RuntimeError):
            pass

        def request(provider, method, url, *, json=None, headers=None, timeout=30):
            self.calls.append((provider, method, url, json))
            answer = self.responses.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        vars(module).update(ProviderNotSignedIn=ProviderNotSignedIn, credentialed_provider_request=request)
        self.not_signed_in = ProviderNotSignedIn
        package = sys.modules.get('hermes_cli') or types.ModuleType('hermes_cli')
        patcher = patch.dict(sys.modules, {'hermes_cli': package, 'hermes_cli.plugin_provider_requests': module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_requests_carry_no_token_and_go_to_the_declared_api(self):
        self.responses = [Response(body=b'{"fulcra_userid": "u"}')]
        api = self.client.client()
        self.assertEqual(api.fulcra_api('/user/v1alpha1/info', query={'a': '1'}), b'{"fulcra_userid": "u"}')
        provider, method, url, body = self.calls[0]
        self.assertEqual((provider, method, url, body), ('fulcra', 'GET', 'https://api.devfulcra.com/user/v1alpha1/info?a=1', None))
        self.assertIsNone(api.fulcra_credentials)

    def test_signed_out_explains_how_to_sign_in(self):
        self.responses = [self.not_signed_in('no')]
        with self.assertRaises(self.client.AuthenticationRequired) as caught:
            self.client.client().fulcra_api('/x')
        self.assertIn('hermes auth add fulcra:fulcra', str(caught.exception))

    def test_errors_and_redirects(self):
        self.responses = [Response(404, b'{"detail": "missing"}')]
        with self.assertRaises(HTTPError) as caught:
            self.client.client().fulcra_api('/x')
        self.assertEqual(caught.exception.code, 404)
        # Same origin: Hermes signs the follow-up too. Another origin: fetched without any credential.
        self.responses = [Response(303, b'', {'location': '/y?z=1'}), Response(body=b'same')]
        self.assertEqual(self.client.client().fulcra_api('/x'), b'same')
        self.assertEqual(self.calls[-1][2], 'https://api.devfulcra.com/y?z=1')
        self.responses = [Response(307, b'', {'location': 'https://storage.example/f?sig=1'})]
        with patch.object(self.client.Client, '_open', return_value=io.BytesIO(b'file')) as opened:
            with self.client.client().fulcra_api('/download', return_http_response=True) as response:
                self.assertEqual(response.read(), b'file')
        self.assertNotIn('Authorization', opened.call_args.args[0].headers)


if __name__ == '__main__':
    unittest.main()
