"""Native API lifetime, shared credentials and finite network deadlines."""
from contextlib import contextmanager
import io
import weakref
import json
import mimetypes
import os
from pathlib import Path
import tempfile
import threading
import time
from urllib.error import HTTPError
import urllib.parse
import urllib.request

from ._vendor.core import FulcraAPI
from ._vendor.credentials import FulcraCredentials

AUTH_LOCK = threading.RLock()
# Only live factory clients retain a generation. Unknown disk replacements start
# a new login, never an inferred identity based on unverified token claims.
_GENERATIONS = weakref.WeakValueDictionary()


class _CredentialGeneration:
    def __init__(self, path, credentials):
        self.path = path
        self.credentials = credentials


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Fulcra request deadline')
    return remaining


@contextmanager
def _auth_lock(deadline):
    if not AUTH_LOCK.acquire(timeout=_remaining(deadline)):
        raise TimeoutError('Fulcra request deadline')
    try:
        _remaining(deadline)
        yield
    finally:
        AUTH_LOCK.release()


def _load_credentials(path):
    return FulcraCredentials.from_json(path.read_text()) if path.is_file() else None


class PrivateRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        origin = urllib.parse.urlsplit(req.full_url)
        target = urllib.parse.urlsplit(newurl)
        if redirected is not None and (origin.scheme, origin.netloc) != (target.scheme, target.netloc):
            redirected.remove_header('Authorization')
        return redirected


class MissingFile(FileNotFoundError):
    pass


def credential_path():
    # Intentionally OS-user shared, identical to the official CLI (not XDG/profile).
    return Path.home() / '.config' / 'fulcra' / 'credentials.json'


def save_credentials(creds, *, path=None):
    path = credential_path() if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.credentials-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(creds.to_json())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Client(FulcraAPI):
    def __init__(self, *, timeout=30, credentials=None, _deadline=None, _generation=None, **kwargs):
        self.deadline = time.monotonic() + timeout if _deadline is None else _deadline
        self._generation = _generation
        # Explicitly injected credentials are independent of OS-user storage.
        super().__init__(credentials=credentials, refresh_callback=self._save_refresh if _generation is not None else None, **kwargs)
        self.oidc._open = self._open

    def _reconcile_credentials(self):
        generation = self._generation
        if generation is not None:
            if _load_credentials(generation.path) != generation.credentials:
                raise ValueError('Fulcra credentials changed; create a new client.')
            self.fulcra_credentials = generation.credentials
        _remaining(self.deadline)

    def _save_refresh(self, creds):
        # Called under AUTH_LOCK. Check again after the exchange so an external
        # login replacement during refresh is not silently overwritten.
        generation = self._generation
        assert generation is not None
        if _load_credentials(generation.path) != generation.credentials:
            raise ValueError('Fulcra credentials changed; create a new client.')
        _remaining(self.deadline)
        save_credentials(creds, path=generation.path)
        generation.credentials = creds

    def _open(self, request):
        return urllib.request.build_opener(PrivateRedirect()).open(request, timeout=_remaining(self.deadline))

    def refresh_access_token(self):
        with _auth_lock(self.deadline):
            self._reconcile_credentials()
            return super().refresh_access_token()

    def fulcra_api(self, *args, **kwargs):
        with _auth_lock(self.deadline):
            self._reconcile_credentials()
            if kwargs.get('authenticated', True) and self.fulcra_credentials is None:
                raise ValueError('Authenticate with fulcra_auth first.')
            return super().fulcra_api(*args, **kwargs)

    def file_stat(self, path, user_id=None):
        try:
            return self.resolve_filepath(path, all_versions=user_id is None,
                                         fulcra_userid=user_id, include_deleted=user_id is None)
        except Exception as exc:
            if type(exc) is Exception and str(exc) == f'File not found in Fulcra: {path}':
                raise MissingFile(path) from None
            raise

    def read_file(self, path, user_id=None):
        try:
            files = self.resolve_filepath(path, fulcra_userid=user_id)
        except Exception as exc:
            if type(exc) is Exception and str(exc) == f'File not found in Fulcra: {path}':
                raise MissingFile(path) from None
            raise
        with self.download_file(files[0]['id'], fulcra_userid=user_id) as response:
            return response.read()

    def write_file(self, path, data):
        return self.upload_file(io.BytesIO(data), mimetypes.guess_type(path)[0] or 'application/octet-stream', len(data), path)


def client(*, timeout=30):
    deadline = time.monotonic() + timeout
    with _auth_lock(deadline):
        path = credential_path()
        creds = _load_credentials(path)
        _remaining(deadline)
        generation = _GENERATIONS.get(path)
        if generation is None or generation.credentials != creds:
            generation = _CredentialGeneration(path, creds)
            _GENERATIONS[path] = generation
        return Client(credentials=creds, _deadline=deadline, _generation=generation)


def auth_start():
    api = Client()
    code, uri, user_code, expires, interval = api.oidc.get_device_code()
    return {'verification_uri': uri, 'user_code': user_code, 'device_code': code,
            'expires_in': expires, 'interval': interval}


def auth_finish(device_code):
    # One exchange, never polling/sleeping on the turn thread.
    api = Client()
    try:
        creds = api.oidc.get_token('urn:ietf:params:oauth:grant-type:device_code', {'device_code': device_code})
    except HTTPError as exc:
        with exc:
            status = json.loads(exc.read()).get('error')
        if status in ('authorization_pending', 'slow_down') or exc.code == 429:
            return {'status': 'pending', 'retry_after': 10 if status == 'slow_down' or exc.code == 429 else 5}
        raise ValueError('Authorization failed or expired; start a new flow.') from None
    with _auth_lock(api.deadline):
        save_credentials(creds)
    return {'status': 'authorized'}
