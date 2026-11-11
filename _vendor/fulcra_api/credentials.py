# Extracted from fulcra_api 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
import base64
import json
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import Optional, Self

def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.astimezone()

def _to_stored(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return _aware(dt).astimezone().replace(tzinfo=None).isoformat()

def _from_stored(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return _aware(datetime.fromisoformat(value))

def jwt_expiration(token: Optional[str]) -> Optional[datetime]:
    if not token or token.count('.') != 2:
        return None
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))['exp']
        return datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except (ValueError, KeyError, TypeError):
        return None

@dataclass
class FulcraCredentials:
    access_token: Optional[str] = None
    access_token_expiration: Optional[datetime] = None
    refresh_token: Optional[str] = None
    refresh_token_expiration: Optional[datetime] = None
    id_token: Optional[str] = None
    id_token_expiration: Optional[datetime] = None

    def expires_at(self) -> Optional[datetime]:
        exp = jwt_expiration(self.access_token)
        if exp is not None:
            return exp
        if self.access_token_expiration is not None:
            return _aware(self.access_token_expiration)
        return None

    def is_expired(self, leeway: timedelta=timedelta(0)) -> bool:
        if self.access_token is None:
            return True
        expires_at = self.expires_at()
        if expires_at is None:
            return True
        return expires_at <= datetime.now(timezone.utc) + leeway

    def to_json(self) -> str:
        return json.dumps({'access_token': self.access_token, 'access_token_expiration': _to_stored(self.access_token_expiration), 'refresh_token': self.refresh_token, 'refresh_token_expiration': _to_stored(self.refresh_token_expiration), 'id_token': self.id_token, 'id_token_expiration': _to_stored(self.id_token_expiration)})

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        o = json.loads(data)
        for key in ('access_token_expiration', 'refresh_token_expiration', 'id_token_expiration'):
            o[key] = _from_stored(o.get(key))
        known_fields = {f.name for f in fields(cls)}
        return FulcraCredentials(**{k: v for k, v in o.items() if k in known_fields})
