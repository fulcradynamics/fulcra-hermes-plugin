"""Fulcra API calls with the sign-in Hermes holds, and finite network deadlines."""
import io
import mimetypes
import time
from urllib.error import HTTPError
import urllib.parse
import urllib.request

from ._vendor.fulcra_api.core import FulcraAPI

# Path B thin slice (PLAT-1069): Hermes signs in to Fulcra through the plugin's oauth: entry in plugin.yaml
# (Auth0 via the sign-in relay, PLAT-1056) and attaches the token to each request. Dev tenant only for now.
PROVIDER = 'fulcra'
API = 'https://api.devfulcra.com'
SIGN_IN = 'hermes auth add fulcra:fulcra'
REDIRECTS = {301, 302, 303, 307, 308}


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Fulcra request deadline')
    return remaining


class MissingFile(FileNotFoundError):
    pass


class AuthenticationRequired(ValueError):
    """Hermes has no Fulcra sign-in for this profile."""


class _Response(io.BytesIO):
    """What the vendored client reads from urllib: a readable body with status and headers."""

    def __init__(self, status, headers, body):
        super().__init__(body)
        self.status, self.headers = status, headers


class Client(FulcraAPI):
    def __init__(self, *, timeout=30, **kwargs):
        self.deadline = time.monotonic() + timeout
        super().__init__(oidc_audience=API + '/', **kwargs)

    def _open(self, request):
        # Only for requests that carry no Fulcra credential (signed upload and download URLs).
        return urllib.request.urlopen(request, timeout=_remaining(self.deadline))

    def refresh_if_expiring(self):
        pass  # Hermes refreshes the sign-in.

    def fulcra_api(self, url_path, method='GET', query=None, data=None, return_http_response=False,
                   content_type='application/json', authenticated=True):
        from hermes_cli.plugin_provider_requests import ProviderNotSignedIn, credentialed_provider_request
        url = API + url_path + ('?' + urllib.parse.urlencode(query, doseq=True) if query else '')
        if data is not None and content_type != 'application/json':
            raise ValueError(f'{content_type} bodies are not supported in this build')
        try:
            response = credentialed_provider_request(PROVIDER, method, url, json=data, timeout=_remaining(self.deadline),
                                                     headers={'User-Agent': self.user_agent})
        except ProviderNotSignedIn:
            raise AuthenticationRequired(f'Sign in to Fulcra in a terminal: {SIGN_IN}') from None
        if response.status in REDIRECTS and response.headers.get('location'):
            location = urllib.parse.urljoin(url, response.headers['location'])
            if urllib.parse.urlsplit(location)[:2] == urllib.parse.urlsplit(API)[:2]:
                path = urllib.parse.urlsplit(location)
                return self.fulcra_api(path.path + ('?' + path.query if path.query else ''), 'GET',
                                       return_http_response=return_http_response)
            # Another origin (a signed download URL) gets no credential.
            opened = self._open(urllib.request.Request(location, headers={'User-Agent': self.user_agent}))
            return opened if return_http_response else opened.read()
        if response.status >= 400:
            raise HTTPError(url, response.status, 'Fulcra API error', response.headers, io.BytesIO(response.body))
        return _Response(response.status, response.headers, response.body) if return_http_response else response.body

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
    return Client(timeout=timeout)
