"""Public schemas share the exact validation contract used by the CLI handlers.

Definitions live beside their handlers in tools.py so validation and the model's
schema cannot drift. No SDK, subprocess or runtime configuration is loaded here.
"""
from .tools import TOOL_SCHEMAS

AUTH_GET_URL = TOOL_SCHEMAS["fulcra_auth"]
AUTH_SUBMIT_CODE = TOOL_SCHEMAS["fulcra_auth_device"]
GET_CATALOG = TOOL_SCHEMAS["fulcra_data_catalog"]
