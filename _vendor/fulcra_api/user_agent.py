# Extracted from fulcra_api 4a4769152e9770406fe66113e49e555f70db9201; see PROVENANCE.md.
import re
import sys
from . import __version__
_EXTRA = re.compile('[\\x20-\\x7e]+')

def default_user_agent() -> str:
    major, minor = sys.version_info[:2]
    return f'fulcra-api/{__version__} python/{major}.{minor}'

def build_user_agent(extra: str | None=None) -> str:
    if extra is None:
        return default_user_agent()
    extra = extra.strip()
    if not extra or not _EXTRA.fullmatch(extra):
        raise ValueError("user_agent_extra must be non-empty printable ASCII, e.g. 'my-tool/1.0'")
    return f'{default_user_agent()} {extra}'
