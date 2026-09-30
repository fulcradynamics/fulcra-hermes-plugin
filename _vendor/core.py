# Extracted from fulcra-api-python 66949bac42920c841facd567a02d6d6c4e01e824; see PROVENANCE.md.
import base64
import datetime
import http.client
import io
import json
import os
import os.path
import urllib.parse
import urllib.request
from pathlib import PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError
import jsonschema
from .credentials import FulcraCredentials
from .oidc import FulcraOIDCProvider
FULCRA_OIDC_DOMAIN = os.environ.get('FULCRA_OIDC_DOMAIN', 'fulcra.us.auth0.com')
FULCRA_OIDC_CLIENT_ID = os.environ.get('FULCRA_OIDC_CLIENT_ID', '48p3VbMnr5kMuJAUe9gJ9vjmdWLdnqZt')
FULCRA_OIDC_AUDIENCE = os.environ.get('FULCRA_OIDC_AUDIENCE', 'https://api.fulcradynamics.com/')
FULCRA_OIDC_SCOPE = os.environ.get('FULCRA_OIDC_SCOPE', 'openid profile name email offline_access')
UNSET: Any = object()

def _boundary_timestamp(value: Any, name: str) -> Any:
    if value is UNSET or value is None:
        return value
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f'{name} must be a valid ISO 8601 timestamp, not {value!r}') from None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{name} must include a timezone offset')
    return value

class FulcraDataAccessMixin:

    def metric_samples(self, start_time: Union[str, datetime.datetime], end_time: Union[str, datetime.datetime], metric: str, fulcra_userid: Optional[str]=None) -> List[Dict]:
        params = {'start_time': start_time, 'end_time': end_time, 'metric': metric}
        resp = self.fulcra_api(self._v0_data_path('metric_samples', fulcra_userid), query=params)
        return json.loads(resp)

class FulcraAPI(FulcraDataAccessMixin):

    def __init__(self, oidc_domain: Optional[str]=None, oidc_client_id: Optional[str]=None, oidc_scope: Optional[str]=None, oidc_audience: Optional[str]=None, access_token: Optional[str]=None, access_token_expiration: Optional[datetime.datetime]=None, refresh_token: Optional[str]=None, credentials: Optional[FulcraCredentials]=None, refresh_callback: Optional[Callable]=None):
        self.oidc = FulcraOIDCProvider(domain=oidc_domain or FULCRA_OIDC_DOMAIN, client_id=oidc_client_id or FULCRA_OIDC_CLIENT_ID, scope=oidc_scope or FULCRA_OIDC_SCOPE, audience=oidc_audience or FULCRA_OIDC_AUDIENCE)
        self.fulcra_credentials = credentials
        audience_url = urllib.parse.urlparse(self.oidc.audience)
        self.fulcra_api_domain = audience_url.hostname
        self.fulcra_api_is_http = False
        if audience_url.scheme == 'http':
            if self.fulcra_api_domain in ['localhost', '127.0.0.1']:
                self.fulcra_api_is_http = True
            else:
                raise ValueError('HTTP audience scheme only allowed for localhost')
        self.fulcra_api_port = audience_url.port
        if self.fulcra_credentials is None and (access_token is not None or access_token_expiration is not None or refresh_token is not None):
            kwargs = {}
            if access_token:
                kwargs['access_token'] = access_token
            if access_token_expiration:
                kwargs['access_token_expiration'] = access_token_expiration
            if refresh_token:
                kwargs['refresh_token'] = refresh_token
            self.fulcra_credentials = FulcraCredentials(**kwargs)
        self.refresh_callback = refresh_callback

    def refresh_access_token(self) -> bool:
        if self.fulcra_credentials is None or self.fulcra_credentials.refresh_token is None:
            raise Exception('No refresh token available to refresh the access token.')
        try:
            new_creds = self.oidc.refresh_credentials(self.fulcra_credentials)
        except Exception:
            return False
        if new_creds.refresh_token is None:
            new_creds.refresh_token = self.fulcra_credentials.refresh_token
        self.fulcra_credentials = new_creds
        if self.refresh_callback is not None:
            self.refresh_callback(self.fulcra_credentials)
        return True

    def fulcra_api(self, url_path: str, method: str='GET', query: dict[str, str] | None=None, data: dict | List[dict] | None=None, return_http_response: bool=False, content_type: str='application/json', authenticated: bool=True) -> bytes | http.client.HTTPResponse:
        if authenticated and self.fulcra_credentials is not None and self.fulcra_credentials.is_expired():
            self.refresh_access_token()
        if self.fulcra_api_is_http:
            proto = 'http'
        else:
            proto = 'https'
        host = self.fulcra_api_domain
        if self.fulcra_api_port:
            host = f'{host}:{self.fulcra_api_port}'
        if query:
            url_query = urllib.parse.urlencode(query, doseq=True)
        else:
            url_query = ''
        url = urllib.parse.urlunparse((proto, host, url_path, '', url_query, ''))
        if authenticated:
            headers = {'Authorization': f'Bearer {self.fulcra_credentials.access_token}'}
        else:
            headers = {}
        if data is not None:
            headers['Content-Type'] = content_type
            if content_type == 'application/x-jsonl':
                if isinstance(data, list):
                    ds = '\n'.join((json.dumps(record) for record in data)).encode('UTF-8')
                else:
                    ds = json.dumps(data).encode('UTF-8')
                ds += b'\n'
            else:
                ds = json.dumps(data).encode('UTF-8')
            headers['Content-Length'] = str(len(ds))
        else:
            ds = None
        req = urllib.request.Request(url=url, data=ds, headers=headers, method=method)
        try:
            response = self._open(req)
            if return_http_response:
                return response
            return response.read()
        except HTTPError as exc:
            if exc.status == 303:
                location = exc.headers.get('Location')
                if location:
                    parsed = urllib.parse.urlparse(location)
                    path = parsed.path if parsed.path else location
                    return self.fulcra_api(path, method='GET', return_http_response=return_http_response, authenticated=authenticated)
            raise

    def fulcra_v1alpha1_api_path(self, path: str, params: Optional[dict[str, str]]=None) -> bytes:
        return self.fulcra_api(f'/data/v1alpha1/{path}', query=params if params else {})

    def fulcra_v1_records(self, query: str, fulcra_userid: Optional[str]=None) -> bytes:
        params = {'q': query}
        if fulcra_userid:
            params['fulcra_userid'] = fulcra_userid
        return self.fulcra_api('/data/v1/records', query=params)

    def _v0_data_path(self, operation: str, fulcra_userid: Optional[str]=None) -> str:
        if fulcra_userid is None:
            fulcra_userid = self.get_fulcra_userid()
        return f'/data/v0/{fulcra_userid}/{operation}'

    @staticmethod
    def _decode_jwt_claims(token: str) -> dict:
        segs = token.split('.')
        if len(segs) < 2:
            raise Exception('Token is in an incorrect format.')
        payload = segs[1] + '=='
        return json.loads(base64.urlsafe_b64decode(payload))

    def get_token_claims(self) -> dict:
        if self.fulcra_credentials is None or self.fulcra_credentials.access_token is None:
            raise Exception('Authorization must occur before retrieving token claims.')
        return self._decode_jwt_claims(self.fulcra_credentials.access_token)

    def get_fulcra_userid(self) -> str:
        claims = self.get_token_claims()
        return claims['fulcradynamics.com/userid']

    def v1_catalog(self, data_type: str | None=None, category: str | None=None, fulcra_userid: str | None=None) -> List[Dict]:
        params = {}
        if data_type:
            params['data_type'] = data_type
        if category:
            params['category'] = category
        if fulcra_userid:
            params['fulcra_userid'] = fulcra_userid
        resp = self.fulcra_api('/data/v1/catalog', query=params)
        return json.loads(resp)

    def v1_catalog_data_type(self, data_type: str, api_version: str, fulcra_userid: str | None=None) -> Dict:
        params = {}
        if fulcra_userid is not None:
            params['fulcra_userid'] = fulcra_userid
        uri = f'/data/v1/catalog/{data_type}/{api_version}'
        resp = self.fulcra_api(uri, query=params)
        return json.loads(resp)

    def v1_catalog_schema(self, data_type: str, api_version: str, fulcra_userid: str | None=None) -> Dict:
        params = {}
        if fulcra_userid is not None:
            params['fulcra_userid'] = fulcra_userid
        uri = f'/data/v1/catalog/{data_type}/{api_version}/schema'
        resp = self.fulcra_api(uri, query=params)
        return json.loads(resp)

    def resolve_data_type(self, data_type: str, api_version: str | None=None, fulcra_userid: str | None=None) -> List[Dict]:
        error_info = [f'for data type {data_type}']
        if api_version is not None:
            error_info.append(f'with API version {api_version}')
        if fulcra_userid is not None:
            error_info.append(f'with user ID {fulcra_userid}')
        try:
            if api_version is not None and fulcra_userid is not None:
                dt = self.v1_catalog_data_type(data_type=data_type, api_version=api_version, fulcra_userid=fulcra_userid)
                return [dt]
            else:
                data_types = self.v1_catalog(data_type=data_type, fulcra_userid=fulcra_userid)
        except HTTPError as exc:
            if exc.code == 404:
                raise ValueError(f"Type not found {' '.join(error_info)}")
            else:
                raise
        if api_version is not None:
            data_types = [dt for dt in data_types if dt['api_version'] == api_version]
        user_ids = {dt['fulcra_userid'] for dt in data_types}
        if fulcra_userid is None and len(user_ids) > 1:
            authenticated_user_id = self.get_fulcra_userid()
            if authenticated_user_id in user_ids:
                data_types = [dt for dt in data_types if dt['fulcra_userid'] == authenticated_user_id]
                user_ids = {authenticated_user_id}
        if len(data_types) == 0:
            raise ValueError(f"Type not found {' '.join(error_info)}")
        if len(user_ids) > 1:
            raise ValueError(f"Multiple user IDs found {' '.join(error_info)} ({', '.join(sorted(user_ids))})")
        return data_types

    def create_datashare(self, datashare_name: str, fulcra_data_types: List[str], allowed_user_ids: Optional[List[str]]=None, share_all_data: bool=False, time_start: Optional[str | datetime.datetime]=None, time_end: Optional[str | datetime.datetime]=None, allowed_group_ids: Optional[List[str]]=None) -> dict:
        time_start = _boundary_timestamp(time_start, 'time_start')
        time_end = _boundary_timestamp(time_end, 'time_end')
        permissions = [{'allowed_fulcra_userid': user_id} for user_id in allowed_user_ids or []]
        fulcra_user_name = self.get_fulcra_userid()
        datashare_body: dict = {'datashare_name': datashare_name, 'fulcra_user_name': fulcra_user_name, 'time_start': time_start.isoformat() if time_start else None, 'time_end': time_end.isoformat() if time_end else None, 'fulcra_data_types': fulcra_data_types, 'share_all_data': share_all_data, 'permissions': permissions}
        if allowed_group_ids is not None:
            datashare_body['group_permissions'] = [{'allowed_group_id': group_id} for group_id in allowed_group_ids]
        resp = self.fulcra_api('/user/v1/datashare', data=datashare_body, method='POST')
        return json.loads(resp)

    def update_datashare(self, datashare_id: str, datashare_name: Optional[str]=UNSET, fulcra_data_types: Optional[List[str]]=UNSET, allowed_user_ids: Optional[List[str]]=UNSET, share_all_data: Optional[bool]=UNSET, time_start: Optional[str | datetime.datetime]=UNSET, time_end: Optional[str | datetime.datetime]=UNSET, allowed_group_ids: Optional[List[str]]=UNSET) -> dict:
        time_start = _boundary_timestamp(time_start, 'time_start')
        time_end = _boundary_timestamp(time_end, 'time_end')
        datashare_body: dict = {}
        for key, value in (('datashare_name', datashare_name), ('fulcra_data_types', fulcra_data_types), ('share_all_data', share_all_data)):
            if value is not UNSET:
                datashare_body[key] = value
        for key, value in (('time_start', time_start), ('time_end', time_end)):
            if value is not UNSET:
                datashare_body[key] = value.isoformat() if value else None
        if allowed_user_ids is not UNSET:
            datashare_body['permissions'] = [{'allowed_fulcra_userid': user_id} for user_id in allowed_user_ids or []]
        if allowed_group_ids is not UNSET:
            datashare_body['group_permissions'] = [{'allowed_group_id': group_id} for group_id in allowed_group_ids or []]
        resp = self.fulcra_api(f'/user/v1/datashare/{datashare_id}', data=datashare_body, method='PUT')
        return json.loads(resp)

    def get_datashares(self) -> List[dict]:
        resp = self.fulcra_api('/user/v1/datashare')
        return json.loads(resp)

    def delete_datashare(self, datashare_id: str):
        self.fulcra_api(f'/user/v1/datashare/{datashare_id}', method='DELETE')

    def data_updates(self, start_time: str | datetime.datetime, end_time: str | datetime.datetime, fulcra_userid: str | None=None) -> dict:
        params = {'start_time': start_time, 'end_time': end_time}
        if fulcra_userid is not None:
            params['fulcra_userid'] = fulcra_userid
        resp = self.fulcra_api('/data/v1/updates', query=params)
        return json.loads(resp)

    def get_shared_datasets(self) -> List[Dict]:
        resp = self.fulcra_api('/user/v1/dataset')
        return json.loads(resp)

    def delete_dataset_permission(self, grant_id: str):
        self.fulcra_api(f'/user/v1/dataset/{grant_id}', method='DELETE')

    def list_shared_data_types(self, fulcra_userid: str, start_time: str | datetime.datetime, end_time: str | datetime.datetime) -> dict:
        params = {'start_time': start_time, 'end_time': end_time}
        resp = self.fulcra_api(f'/user/v1/shared/{fulcra_userid}/data_types', query=params)
        return json.loads(resp)

    def get_user_info(self) -> Dict:
        resp = self.fulcra_api('/user/v1alpha1/info')
        return json.loads(resp)

    def tags(self) -> list[dict[str, str]]:
        resp = self.fulcra_api('/user/v1alpha1/tag')
        return json.loads(resp)

    def create_tag(self, tag_name: str) -> dict[str, str]:
        resp = self.fulcra_api('/user/v1alpha1/tag', method='POST', data={'name': tag_name})
        return json.loads(resp)

    def create_tags(self, tag_names: list[str]) -> list[dict[str, str]]:
        existing_tags = self.tags()
        result: list[dict[str, str]] = []
        for tag_name in tag_names:
            try:
                tag = next((t for t in existing_tags if t['name'] == tag_name))
            except StopIteration:
                tag = self.create_tag(tag_name)
            result.append(tag)
        return result

    def create_annotation(self, annotation_type: str, name: str, description: Optional[str], tags: List[str], metric_kind: Optional[str]=None, value: Optional[Any]=None, unit: Optional[str]=None, scale_labels: Optional[List[str]]=None) -> Dict:
        tag_ids = []
        if len(tags) > 0:
            tag_ids = [t['id'] for t in self.create_tags(tags)]
        spec = None
        measurement_spec = None
        if annotation_type == 'duration':
            measurement_spec = {'measurement_type': 'duration', 'value_type': 'duration', 'unit': None}
        elif annotation_type == 'boolean':
            measurement_spec = {'measurement_type': 'boolean', 'value_type': 'boolean', 'unit': None, 'boolean': {'value': value}}
        elif annotation_type == 'numeric':
            measurement_spec = {'measurement_type': 'custom', 'unit': unit, 'custom': {'value': value}}
        elif annotation_type == 'scale':
            spec = {'scale': {'label_mapping': {'mapping_type': 'string', 'string': {'mapping': {i + 1: v for i, v in enumerate(scale_labels)} if scale_labels else None}}}}
            measurement_spec = {'measurement_type': 'scale', 'value_type': 'integer', 'unit': None, 'scale': {'value': None, 'min_allowed': 1, 'max_allowed': 5}}
        if metric_kind is not None and measurement_spec is not None:
            measurement_spec['metric_kind'] = metric_kind
        annotation_body = {'name': name, 'description': description or '', 'annotation_type': annotation_type, 'measurement_spec': measurement_spec, 'tags': tag_ids, 'spec': spec}
        resp = self.fulcra_api('/user/v1alpha1/annotation', data=annotation_body, method='POST')
        return json.loads(resp)

    def delete_annotation(self, annotation_id: str):
        self.fulcra_api(f'user/v1alpha1/annotation/{annotation_id}', method='DELETE')

    def restore_annotation(self, annotation_id: str):
        resp = self.fulcra_api(f'user/v1alpha1/annotation/{annotation_id}/cancel_deletion', method='POST')
        return json.loads(resp)

    def record_data_type(self, data_type: str, records: List[dict], api_version: str) -> dict:
        resp = self.fulcra_api(f'/ingest/v1/record/{data_type}', method='POST', query={'api_version': api_version}, data=records, content_type='application/x-jsonl')
        return json.loads(resp)

    def validate_records(self, data_type: str, records: List[dict], api_version: str='v1alpha1') -> list[tuple[int, str, jsonschema.ValidationError]]:
        schema = self.v1_catalog_schema(data_type, api_version)
        errors = []
        for idx, record in enumerate(records):
            try:
                jsonschema.validate(instance=record, schema=schema, format_checker=jsonschema.FormatChecker())
            except jsonschema.ValidationError as e:
                error_msg = e.message
                if e.path:
                    error_msg += f" (path: {'.'.join((str(p) for p in e.path))})"
                errors.append((idx, error_msg, e))
        return errors

    def list_files(self, path: str='/', state: str='uploaded', fulcra_userid: str | None=None, base_name: str | None=None) -> dict:
        params = {'path': path, 'state': state}
        if fulcra_userid:
            params['fulcra_userid'] = fulcra_userid
        if base_name:
            params['name'] = base_name
        resp = self.fulcra_api('/input/v1/file_upload', query=params)
        return json.loads(resp)

    def resolve_filepath(self, filepath: str, all_versions: bool=False, fulcra_userid: str | None=None, include_deleted: bool=False) -> list[dict]:
        p = PurePosixPath(filepath)
        path = p.parent
        name = p.name
        if all_versions:
            state = 'uploaded,archived'
        else:
            state = 'uploaded'
        if include_deleted:
            state += ',deleted'
        params = {'path': str(path), 'name': str(name), 'state': state}
        if fulcra_userid:
            params['fulcra_userid'] = fulcra_userid
        resp = self.fulcra_api('/input/v1/file_upload', query=params)
        rbody = json.loads(resp)
        if all_versions:
            files = sorted(rbody['files'], key=lambda d: d['uploaded_at'], reverse=True)
            if (len(files) == 0 or files[0]['state'] != 'uploaded') and (not include_deleted):
                raise Exception(f'File not found in Fulcra: {filepath}')
        else:
            files = rbody['files']
            if len(files) == 0:
                raise Exception(f'File not found in Fulcra: {filepath}')
        return files

    def upload_file(self, data: io.BufferedReader, file_type: str, file_size: int, filepath: str) -> dict:
        path = PurePosixPath(filepath)
        file_info = {'content_length': file_size, 'content_type': file_type, 'name': str(path.name), 'path': str(path.parent)}
        resp = self.fulcra_api('/input/v1/file_upload', data=file_info, method='POST')
        r = json.loads(resp)
        upload_url = r['url']
        req = urllib.request.Request(upload_url, data=data, headers={'Content-Length': file_size, 'Content-Type': file_type}, method='POST')
        upload_resp = self._open(req)
        return r

    def download_file(self, file_id: str, fulcra_userid: str | None=None) -> http.client.HTTPResponse:
        params = {}
        if fulcra_userid:
            params['fulcra_userid'] = fulcra_userid
        resp = self.fulcra_api(f'/input/v1/file_upload/{file_id}/download', query=params, return_http_response=True)
        return resp

    def delete_file(self, file_id: str):
        self.fulcra_api(f'/input/v1/file_upload/{file_id}', method='DELETE')

    def restore_file(self, file_id: str):
        return json.loads(self.fulcra_api(f'/input/v1/file_upload/{file_id}/restore', method='POST'))

    def group_participant(self, group_id: str, participant_id: str) -> 'FulcraGroupParticipant':
        return FulcraGroupParticipant(self, group_id, participant_id)

class FulcraGroupParticipant(FulcraDataAccessMixin):

    def __init__(self, client: FulcraAPI, group_id: str, participant_id: str):
        self.client = client
        self.group_id = group_id
        self.participant_id = participant_id

    def fulcra_api(self, url_path: str, method: str='GET', query: Optional[dict]=None, data: Optional[Union[dict, List[dict]]]=None, return_http_response: bool=False, content_type: str='application/json') -> Any:
        return self.client.fulcra_api(url_path, method=method, query=query, data=data, return_http_response=return_http_response, content_type=content_type)

    def _v0_data_path(self, operation: str, fulcra_userid: Optional[str]=None) -> str:
        if fulcra_userid is not None:
            raise ValueError('fulcra_userid cannot be specified when accessing group participant data')
        return f'/data/v0/pool/{self.group_id}/participant/{self.participant_id}/{operation}'

    def _v1_group_params(self, params: Optional[dict]) -> dict:
        params = dict(params) if params else {}
        if params.get('fulcra_userid') is not None:
            raise ValueError('fulcra_userid cannot be specified when accessing group participant data')
        params['pool_id'] = self.group_id
        params['participant_id'] = self.participant_id
        return params

    def fulcra_v1alpha1_api_path(self, path: str, params: Optional[dict[str, str]]=None) -> bytes:
        return self.client.fulcra_v1alpha1_api_path(path, self._v1_group_params(params))
