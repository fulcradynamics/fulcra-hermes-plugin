# Development

Python 3.11+ with `jsonschema` 4.x; no other runtime dependencies.

    python -m unittest discover -s tests -v
    hermes plugins validate .
    hermes plugins doctor . --ci
    git diff --check

`tests/test_vendor.py` also runs when `FULCRA_API_PYTHON` and `FULCRA_CONTEXT_MCP` point to checkouts at the pinned revisions.

## Layout

- `tools.py`: tool schemas and handlers.
- `messages.py`: the receive tool and its per-agent cursors.
- `whats_new.py`: the what's-new hooks, settings and `/fulcra` command.
- `client.py`: credentials, deadlines and redirect handling around the vendored API client.
- `skills/`: adapted from the Fulcra OpenAI plugin's skills (each names its source in `metadata.origin`).
- `_vendor/`: code extracted from upstream; see [provenance](../_vendor/PROVENANCE.md).

Registration has no network access, writes or background work. What's-new checks run in a background thread after a reply and never block a turn.

## Native Hermes probes

With an installed Hermes, run the probe with its Python and source in a disposable, offline home:

    python tests/native_hermes_probe.py /path/to/hermes/python /path/to/hermes/source --validate
    python tests/native_hermes_probe.py /path/to/hermes/python /path/to/hermes/source --doctor
    python tests/native_hermes_probe.py /path/to/hermes/python /path/to/hermes/source

## Acceptance

`tests/acceptance/` holds end-to-end scenarios: a real Hermes with the plugin installed, driven turn by turn against test accounts, with a tester playing the user and the contact.
