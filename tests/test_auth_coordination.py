"""Offline credential generations and shared absolute deadline regressions."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import importlib
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_tools import load_tools


class AuthCoordinationTests(unittest.TestCase):
    def setUp(self):
        load_tools()
        self.native = importlib.import_module('tool_fixture_plugin.client')
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(root) / 'credentials.json'
        self.enterContext(patch.object(self.native, 'credential_path', return_value=self.path))
        self.enterContext(patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network')))

    def creds(self, token='old', refresh='r0', expired=True):
        return self.native.FulcraCredentials(
            access_token=token, refresh_token=refresh,
            access_token_expiration=datetime.now() + timedelta(seconds=-1 if expired else 3600))

    @contextmanager
    def contention(self):
        acquired, release = threading.Event(), threading.Event()
        def hold():
            with self.native.AUTH_LOCK:
                acquired.set()
                release.wait(2)
        worker = threading.Thread(target=hold)
        worker.start()
        self.assertTrue(acquired.wait(1))
        try:
            yield
        finally:
            release.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def test_two_factory_clients_share_rotated_generation(self):
        self.native.save_credentials(self.creds())
        a, b = self.native.client(), self.native.client()
        attempted, sent, errors = [], [], []
        barrier = threading.Barrier(2)
        def refresh(old):
            attempted.append(old.refresh_token)
            if len(attempted) > 1:
                raise ValueError('Refresh token already consumed')
            return self.creds('new', 'r1', False)
        def opened(req):
            sent.append(req.get_header('Authorization'))
            return io.BytesIO(b'[]')
        def run(api):
            try:
                barrier.wait(2)
                api.v1_catalog()
            except Exception as exc:
                errors.append(exc)
        with patch.object(a.oidc, 'refresh_credentials', side_effect=refresh), patch.object(b.oidc, 'refresh_credentials', side_effect=refresh), patch.object(a, '_open', side_effect=opened), patch.object(b, '_open', side_effect=opened):
            workers = [threading.Thread(target=run, args=(api,)) for api in (a, b)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(3)
                self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(attempted, ['r0'])
        self.assertEqual(sent, ['Bearer new', 'Bearer new'])
        self.assertEqual(self.native.client().fulcra_credentials.refresh_token, 'r1')

    def test_account_change_does_not_adopt_or_overwrite_new_login(self):
        for expired in (True, False):
            with self.subTest(expired=expired):
                self.native.save_credentials(self.creds(expired=expired))
                old = self.native.client()
                other = self.creds('other-account', 'other-refresh', False)
                self.native.save_credentials(other)
                with patch.object(old.oidc, 'refresh_credentials', return_value=self.creds('refreshed-old', 'r1', False)) as refresh, patch.object(old, '_open', return_value=io.BytesIO(b'[]')) as opened:
                    with self.assertRaisesRegex(ValueError, 'credentials changed'):
                        old.v1_catalog()
                    refresh.assert_not_called()
                    opened.assert_not_called()
                self.assertEqual(self.native.FulcraCredentials.from_json(self.path.read_text()), other)

    def test_deleted_login_does_not_get_recreated(self):
        self.native.save_credentials(self.creds())
        old = self.native.client()
        self.path.unlink()
        with patch.object(old.oidc, 'refresh_credentials') as refresh:
            with self.assertRaisesRegex(ValueError, 'credentials changed'):
                old.v1_catalog()
            refresh.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_injected_credentials_never_read_or_overwrite_disk(self):
        other = self.creds('other-account', 'other-refresh', False)
        self.native.save_credentials(other)
        api = self.native.Client(credentials=self.creds())
        with patch.object(self.native, 'credential_path', side_effect=AssertionError('Injected client touched disk')), patch.object(api.oidc, 'refresh_credentials', return_value=self.creds('injected-new', 'r1', False)), patch.object(api, '_open', return_value=io.BytesIO(b'[]')):
            self.assertEqual(api.v1_catalog(), [])
        self.assertEqual(self.native.FulcraCredentials.from_json(self.path.read_text()), other)

    def test_account_replacement_during_refresh_is_not_overwritten(self):
        self.native.save_credentials(self.creds())
        api = self.native.client()
        other = self.creds('other-account', 'other-refresh', False)
        def refresh(old):
            self.native.save_credentials(other)
            return self.creds('refreshed-old', 'r1', False)
        with patch.object(api.oidc, 'refresh_credentials', side_effect=refresh), patch.object(api, '_open') as opened:
            with self.assertRaisesRegex(ValueError, 'credentials changed'):
                api.v1_catalog()
            opened.assert_not_called()
        self.assertEqual(self.native.FulcraCredentials.from_json(self.path.read_text()), other)

    def test_uncertain_write_is_not_replayed(self):
        self.native.save_credentials(self.creds(expired=False))
        api = self.native.client()
        with patch.object(api, '_open', side_effect=TimeoutError('uncertain write')) as opened:
            with self.assertRaises(TimeoutError):
                api.fulcra_api('/synthetic-write', method='POST', data={'value': 1})
            opened.assert_called_once()

    def test_refresh_and_request_share_socket_budget(self):
        self.native.save_credentials(self.creds())
        clock = [100.0]
        budgets = []
        def opened(request, *, timeout):
            budgets.append(timeout)
            clock[0] += .02
            return io.BytesIO(b'[]')
        with patch.object(self.native.time, 'monotonic', side_effect=lambda: clock[0]), patch('urllib.request.OpenerDirector.open', side_effect=opened):
            api = self.native.client(timeout=.1)
            def refresh(old):
                api._open('synthetic refresh')
                return self.creds('new', 'r1', False)
            with patch.object(api.oidc, 'refresh_credentials', side_effect=refresh):
                self.assertEqual(api.v1_catalog(), [])
                self.assertEqual(api.v1_catalog(), [])
        self.assertEqual(len(budgets), 3)
        for actual, expected in zip(budgets, (.1, .08, .06)):
            self.assertAlmostEqual(actual, expected)

    def test_factory_lock_wait_is_deadline_bounded(self):
        with self.contention():
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                self.native.client(timeout=.03)
            self.assertLess(time.monotonic() - start, .3)

    def test_request_lock_wait_is_deadline_bounded(self):
        api = self.native.Client(timeout=.03, credentials=self.creds(expired=False))
        with self.contention():
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                api.v1_catalog()
            self.assertLess(time.monotonic() - start, .3)

    def test_factory_load_and_requests_keep_original_deadline(self):
        self.native.save_credentials(self.creds(expired=False))
        clock = [100.0]
        read = Path.read_text
        def delayed_read(path, *args, **kwargs):
            clock[0] += .04
            return read(path, *args, **kwargs)
        with patch.object(self.native.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(Path, 'read_text', delayed_read):
            api = self.native.client(timeout=.1)
            self.assertAlmostEqual(api.deadline, 100.1)
            clock[0] = 100.11
            with self.assertRaises(TimeoutError):
                api.v1_catalog()

    def test_auth_finish_save_lock_uses_exchange_deadline(self):
        api = self.native.Client(timeout=.03)
        with patch.object(self.native, 'Client', return_value=api), patch.object(api.oidc, 'get_token', return_value=self.creds(expired=False)), self.contention():
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                self.native.auth_finish('synthetic-device-code')
            self.assertLess(time.monotonic() - start, .3)
        self.assertFalse(self.path.exists())
