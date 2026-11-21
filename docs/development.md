# Development

The plugin runs inside Hermes on the standard library alone and declares no dependencies, so installing it asks no consent (Hermes treats any `pyproject.toml` dependency or dependency group as packages to install). Tests need FastAPI for the Desktop backend:

    cd tests && uv run --no-project --with fastapi python -m unittest discover -v
    hermes plugins validate .
    git diff --check

Against a fulcra-context-mcp checkout:

    scripts/check-tools.py /path/to/fulcra-context-mcp    # skills call only offered tools; APP_ONLY matches the server
    scripts/check-upstream.py /path/to/claude-plugin      # skills vs the Claude plugin they're adapted from

## How it fits together

Fulcra's tools come from the hosted Fulcra MCP server. `/fulcra connect` adds it to the profile's `mcp_servers` as `fulcra` with `auth: oauth`; Hermes registers an OAuth client, signs in, stores and refreshes the tokens, and offers the tools to the model as `mcp__fulcra__<tool>`. The plugin registers no tools of its own: a plugin toolset named `fulcra` would hide the server's.

- `mcp_api.py`: the server entry, and calls to the server's tools through `ctx.dispatch_tool`.
- `whats_new.py`: the what's-new hooks. A due check runs in a background thread after a reply and its findings go into the next turn.
- `messages.py`: which shares are contact channels and which records are messages for this agent (validated against `skills/connect-our-agents/references/channel-fields.json`).
- `commands.py`: `/fulcra` and `hermes fulcra` (`connect`, `status`, `setup`). In a terminal, `connect` offers to run `hermes mcp login fulcra`; that is the plugin's only subprocess, and it runs only if the user says yes.
- `dashboard/plugin_api.py`: backend routes for the Desktop page (`/status`, `/connect`, `/ping`), through the plugin's own `ctx`. Hermes connects MCP servers when a session starts, so tools answer once any chat has started in that backend.
- `desktop/plugin.js`: the **Agents I Know** page and the `::fulcra-agents-i-know` transcript directive. Sign-in uses Hermes's own gateway RPC (`mcp.servers.oauth.start`/`poll`) through `host.request`.
- `skills/`: adapted from the Claude Fulcra plugin; `provenance.json` records each source.

Registration has no network access, writes or background work.

## Live checks

`scripts/desktop_backend_check.py` drives a `hermes serve` backend the way the Desktop page does (status, connect, sign-in through the gateway RPC, ping before and after a session).

## Acceptance

`tests/acceptance/` holds end-to-end scenarios: a real Hermes with the plugin installed, driven turn by turn against test accounts, with a tester playing the user and the contact.
