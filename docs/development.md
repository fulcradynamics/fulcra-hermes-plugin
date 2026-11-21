# Development

The plugin runs inside Hermes on the standard library alone and declares no dependencies, so installing it asks no consent (Hermes treats any `pyproject.toml` dependency or dependency group as packages to install). Tests need FastAPI for the Desktop backend:

    cd tests && uv run --no-project --with fastapi python -m unittest discover -v
    hermes plugins validate .
    git diff --check

Against a fulcra-context-mcp checkout:

    scripts/check-tools.py /path/to/fulcra-context-mcp    # skills call only offered, non-panel tools
    scripts/check-upstream.py /path/to/claude-plugin      # skills vs the Claude plugin they're adapted from

## How it fits together

Fulcra's tools come from the hosted Fulcra MCP server. The user adds it with `hermes mcp add fulcra --url … --auth oauth` (the plugin never writes Hermes's config; `/fulcra connect` prints the commands still needed); Hermes registers an OAuth client, signs in, stores and refreshes the tokens, and offers the tools to the model as `mcp__fulcra__<tool>`. The plugin registers no tools of its own: a plugin toolset named `fulcra` would hide the server's.

- `mcp_api.py`: reads whether the server is added and granted, prints the setup commands, and calls the server's tools through `ctx.call_mcp`, Hermes's own MCP client. Hermes allows those calls only for servers the user lists in `plugins.entries.fulcra.mcp_allowlist`.
- `whats_new.py`: the what's-new hooks. A due check runs in a background thread after a reply and its findings go into the next turn.
- `messages.py`: which shares are contact channels and which records are messages for this agent (validated against `skills/connect-our-agents/references/channel-fields.json`).
- `commands.py`: `/fulcra` and `hermes fulcra` (`connect` prints the setup commands still needed, `status`, `setup`). No subprocesses and no config writes.
- `dashboard/plugin_api.py`: backend routes for the Desktop page (`/status` with the commands still needed, `/ping`), through the plugin's own `ctx`. Hermes connects MCP servers when a session starts, so Fulcra answers once any chat has started in that backend. A call to a server that isn't connected counts against Hermes's circuit breaker for it, so the page pings only on request.
- `desktop/plugin.js`: the **Agents I Know** page (status, the commands to copy, a ping) and the `::fulcra-agents-i-know` transcript directive. It doesn't sign in or change config; Desktop's own **Capabilities > MCP servers** does that.
- `skills/`: adapted from the Claude Fulcra plugin; `provenance.json` records each source.

Registration has no network access, writes or background work.

A Hermes that is already running when the server is added connects it on its own: a gateway re-reads `config.yaml` within about a minute, and a server added before sign-in waits for its next retry (30 s, doubling up to 10 minutes). `/reload-mcp` in a chat connects it at once.

## Live checks

`scripts/desktop_backend_check.py` drives a `hermes serve` backend the way the Desktop page does (status, then a ping before and after a session).

## Acceptance

`tests/acceptance/` holds end-to-end scenarios: a real Hermes with the plugin installed, driven turn by turn against test accounts, with a tester playing the user and the contact.
