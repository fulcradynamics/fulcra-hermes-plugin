"""Native API lifetime, shared credentials and finite network deadlines."""
import io
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


def save_credentials(creds):
    path = credential_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.credentials-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(creds.to_json())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Client(FulcraAPI):
    def __init__(self, *, timeout=30, credentials=None, **kwargs):
        self.deadline = time.monotonic() + timeout
        super().__init__(credentials=credentials, refresh_callback=save_credentials, **kwargs)
        self.oidc._open = self._open

    def _open(self, request):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Fulcra request deadline')
        return urllib.request.build_opener(PrivateRedirect()).open(request, timeout=remaining)

    def fulcra_api(self, *args, **kwargs):
        if kwargs.get('authenticated', True) and self.fulcra_credentials is None:
            raise ValueError('Authenticate with fulcra_auth first.')
        with AUTH_LOCK:
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
    with AUTH_LOCK:
        path = credential_path()
        creds = FulcraCredentials.from_json(path.read_text()) if path.is_file() else None
    return Client(timeout=timeout, credentials=creds)


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
    with AUTH_LOCK:
        save_credentials(creds)
    return {'status': 'authorized'}
