# Vendored Fulcra API subset

Source: https://github.com/fulcradynamics/fulcra-api-python
Revision: `66949bac42920c841facd567a02d6d6c4e01e824`
License: Apache-2.0; Copyright 2025 Fulcra Dynamics. Full upstream terms retained in [LICENSE](LICENSE).

`python scripts/vendor.py /path/to/checkout` reproduces these files; verify the
checkout is at the pinned revision first. The explicit method allowlist in that
script is the extraction inventory. Files derive from `fulcra_api/{core,oidc,
credentials,records}.py`, not CLI parsers. No upstream file is modified.

Changes:
- Remove unused API methods, dataframe operations, notebook/browser authorization,
  deprecated auth wrappers, blocking polling and code-grant flow. Keep only the
  core/data/group access methods needed by exposed tools and their helpers.
- Remove long method docstrings/comments and format via Python AST unparse.
- Make records' core import relative. Replace `urllib.request.urlopen` calls by
  `self._open` for plugin-owned timeouts and redirect privacy. No endpoint, payload,
  catalog disambiguation, credential serialization or records dispatch rewrites.
- The surrounding adapter uses the upstream OIDC device/token exchanges once per
  tool call; returns pending rather than polling. It writes the same OS-user JSON
  credentials atomically at mode 0600, and preserves upstream refresh behavior.
  No tokens/raw authentication errors enter logs or results.
- The adapter strips Authorization on cross-origin redirects (urllib otherwise
  forwards it), uses finite request budgets, and never retries uncertain mutations.

Runtime dependency: `jsonschema>=4.23,<5` for upstream schema validation and explicit
tool schemas. Its dependencies are attrs, referencing, rpds-py and
jsonschema-specifications (plus version-dependent typing-extensions). HTTP, OAuth,
JSON, time handling and storage use the standard library. No full SDK, pandas,
numpy, pyarrow, click, dateparser or uv dependency.

CLI-only conveniences intentionally removed: natural-language dates, JSONL/text
presentation, tag/source option merging, artificial CLI record attribution and
read/modify/write share flags. Tools accept explicit native values; annotation
source attachment and DeletedRecord tombstones remain. See README for interfaces.

`tests/test_parity.py` compares selected native wire requests, catalog resolution,
version/group/owner records routing, credential serialization and refresh behavior
with the actual pinned upstream source. Local HTTP tests exercise the plugin path.
