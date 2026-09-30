# Development

Python 3.11+, `jsonschema>=4.23,<5` solely for upstream record validation. No SDK install, CLI, uv, pandas, numpy, pyarrow
or dateparser at runtime. See [_vendor provenance](../_vendor/PROVENANCE.md).

    python -m unittest discover -s tests -v
    FULCRA_UPSTREAM=/path/to/pinned/fulcra-api-python python -m unittest discover -s tests -v
    hermes plugins doctor . --ci
    git diff --check

Parity checks import the pinned original core with an import-only pandas sentinel;
selected methods cannot use dataframe operations. Requests are mocked at the actual
upstream module, socket connections blocked, clients pointed to loopback. Native
local-HTTP tests exercise catalog, validation, JSONL ingestion, signed upload,
byte download and refresh persistence using synthetic credentials. Retained workflow
transcripts use a test-only native fixture adapter, not a production CLI transport.

For installed Hermes, use its already-provisioned Python and matching source, not
a bootstrap launcher that might provision another runtime. Disposable homes and
blocked networking keep probes away from live profiles:

    python tests/run_redaction_probe.py --python /existing/runtime/bin/python --source /path/to/hermes --doctor
    python tests/run_redaction_probe.py --python /existing/runtime/bin/python --source /path/to/hermes
    python tests/native_hermes_probe.py /existing/runtime/bin/python /path/to/hermes

These separately invoke real doctor discovery/registration, redaction dispatch,
and native tool/setup/hooks. The bootstrap-only stub prevents provisioning;
real middleware, transport response normalization and slash dispatch remain in use.

## Architecture and limits

`_vendor` is a reproducible minimal upstream extraction. `client.py` owns shared
credential storage and finite socket timeouts; `tools.py` owns explicit schemas,
targeted safety checks and native record/share/file adapters. Tool schemas guide
callers; they are not a blanket argument-validation gate. Ordinary validation is
left to the API. Upstream record validation remains mandatory because ingestion
is asynchronous. Local checks protect action/routing semantics, explicit deletion
and sharing scope, and local-file safety. Record-query times must be converted to
timezone-aware datetimes for upstream query construction; reversed bounds must
not silently become a one-second query. Share timestamps use upstream handling,
without duplicate plugin checks. API validation diagnostics expose only known
location/type vocabulary, never free text, input values, response bodies or URLs.
Workflow modules consume structured
Python values directly. No CLI argument builders or arbitrary method-invocation tool.
Registration has no remote I/O, writes, workers or auth flows.

Ordinary requests have a 30-second budget; startup shares a 25-second budget.
Timeouts are per blocking socket operation and checked between requests, not a hard
wall-clock cancellation of DNS/streaming. Disabling a feature discards in-flight
results but cannot cancel an already-running request. Results are fully read in
memory before preview bounding: no memory/disk quota. Artifact storage retains
baseline POSIX descriptor-relative safeguards and manual retention.

Workspace seeding has no server conditional-create primitive. Re-read and verify,
but coordinate concurrent external writers. Update suppression is a best-effort
path/type heuristic, not an audit log. Profile/account-switch, notification and
mesh limitations remain in [setup](setup.md), [mesh](mesh.md) and the README.
Redaction files are unchanged from the merged baseline; see [scope](redaction.md).
