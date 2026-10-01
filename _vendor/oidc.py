# Extracted from fulcra-api-python 66949bac42920c841facd567a02d6d6c4e01e824; see PROVENANCE.md.
"""OIDC mechanics for authenticating with the Fulcra API"""
import datetime
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from dataclasses import dataclass
from typing import Callable, Optional, Tuple
from .credentials import FulcraCredentials

@dataclass
class FulcraOIDCProvider:
    domain: str
    client_id: str
    scope: str
    audience: str

    def get_device_code(self) -> Tuple[str, str, str, int, int]:
        body = urllib.parse.urlencode({'client_id': self.client_id, 'audience': self.audience, 'scope': self.scope})
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        request = urllib.request.Request(f'https://{self.domain}/oauth/device/code', data=body.encode('UTF-8'), headers=headers, method='POST')
        response = self._open(request)
        if response.status != 200:
            raise Exception(f'could not get device code: {response}')
        bdata = response.read()
        data = json.loads(bdata)
        r = (data['device_code'], data['verification_uri_complete'], data['user_code'], data['expires_in'], data['interval'])
        return r

    def get_token(self, grant_type: str, payload: dict) -> FulcraCredentials:
        payload = {'client_id': self.client_id, 'grant_type': grant_type} | payload
        body = urllib.parse.urlencode(payload)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        request = urllib.request.Request(f'https://{self.domain}/oauth/token', data=body.encode('UTF-8'), headers=headers, method='POST')
        response = self._open(request)
        body = json.loads(response.read())
        if 'access_token' not in body:
            raise Exception('Got invalid response when requesting token')
        access_token = body['access_token']
        expires_in = datetime.datetime.now() + datetime.timedelta(seconds=float(body['expires_in']))
        refresh_token = body.get('refresh_token')
        id_token = body.get('id_token')
        return FulcraCredentials(access_token=access_token, access_token_expiration=expires_in, refresh_token=refresh_token, id_token=id_token)

    def refresh_credentials(self, credentials: FulcraCredentials) -> FulcraCredentials:
        if credentials.refresh_token is None:
            raise Exception('No refresh token available to refresh credentials with')
        payload = {'refresh_token': credentials.refresh_token, 'scope': self.scope}
        return self.get_token('refresh_token', payload)
