# Development

The plugin runs inside Hermes on the standard library alone and declares no dependencies, so installing it asks no consent (Hermes treats any `pyproject.toml` dependency or dependency group as packages to install). Tests need FastAPI for the Desktop backend:

    cd tests && uv run --no-project --with fastapi python -m unittest discover -v
    hermes plugins validate .
    git diff --check

Against a fulcra-context-mcp checkout:

    scripts/check-tools.py /path/to/fulcra-context-mcp    # skills call only offered, non-panel tools
    scripts/check-upstream.py /path/to/claude-plugin      # skills vs the Claude plugin they're adapted from
    scripts/update-app.py /path/to/fulcra-context-mcp     # copy its current Agents I Know app into desktop/

## How it fits together

Fulcra's tools come from the hosted Fulcra MCP server. The user adds it with `hermes mcp add fulcra --url … --auth oauth` (the plugin never writes Hermes's config; `/fulcra connect` prints the commands still needed); Hermes registers an OAuth client, signs in, stores and refreshes the tokens, and offers the tools to the model as `mcp__fulcra__<tool>`. The plugin registers no tools of its own: a plugin toolset named `fulcra` would hide the server's.

- `mcp_api.py`: reads whether the server is added and granted, prints the setup commands, and calls the server's tools through `ctx.call_mcp`, Hermes's own MCP client. Hermes allows those calls only for servers the user lists in `plugins.entries.fulcra.mcp_allowlist`.
- `whats_new.py`: the what's-new hooks. A due check runs in a background thread after a reply and its findings go into the next turn.
- `messages.py`: which shares are contact channels and which records are messages for this agent (validated against `skills/connect-our-agents/references/channel-fields.json`).
- `commands.py`: `/fulcra` and `hermes fulcra` (`connect` prints the setup commands still needed, `status`, `setup`). No subprocesses and no config writes.
- `dashboard/plugin_api.py`: backend routes for the Desktop page, through the plugin's own `ctx`. Hermes mounts them on first use and keeps them until the backend restarts, even across a reinstall, so `/status` reports `API_VERSION` and the page asks for a restart when it differs from its own; raise both together when the routes change. Routes: `/status` (the commands still needed), `/ping`, `/app` (the app's HTML) and `/call` (the app's tool calls, only those in `mcp_api.APP_TOOLS`).
- `desktop/plugin.js`: the **Agents I Know** page and the `::fulcra-agents-i-know` transcript directive. Until Fulcra is added, granted and answering, the page shows what's missing; it doesn't sign in or change config (Desktop's **Capabilities > MCP servers** does). Then it runs the Agents I Know app in Desktop's `SandboxedFrame` as its MCP Apps host: tool calls go to `/call`, links open in the browser, a message for chat starts a new Hermes chat (followed by the context the app gave for the model), and the theme follows Desktop's. One ping comes first, because calls to a server Hermes hasn't connected count against its circuit breaker.
- `desktop/agents-i-know.html`: the app the Fulcra MCP server offers MCP Apps hosts, copied by `scripts/update-app.py` at the commit in `provenance.json`, so the plugin never loads code from elsewhere. `scripts/check-tools.py` checks `APP_TOOLS` against it.
- `skills/`: adapted from the Claude Fulcra plugin; `provenance.json` records each source.
- `assets/banner.png`: the catalog image (2:1, transparent): the Fulcra logo (the ChatGPT plugin's `assets/icon.png`), the hands from Michelangelo's *Creation of Adam* (public domain) with Adam's as a drawn robot arm, all in Fulcra teal, and the caption. `scripts/banner/make.sh <fulcra-openai-plugin checkout>` rebuilds it; `provenance.json` records the sources. The README shows it, and the catalog entry's `image:` points at it on `raw.githubusercontent.com` at the entry's pinned commit.

Registration has no network access, writes or background work.

A Hermes that is already running when the server is added connects it on its own: a gateway re-reads `config.yaml` within about a minute, and a server added before sign-in waits for its next retry (30 s, doubling up to 10 minutes). `/reload-mcp` in a chat connects it at once.

## Testing in Hermes Desktop

Build Desktop from a Hermes checkout at the version of your installed `hermes` (its `package.json` `engines` names the Node and pnpm versions), then run it against a test home so your own Hermes is untouched:

    cd <hermes>/apps/desktop && pnpm install --frozen-lockfile && pnpm run build
    T=/path/to/test-dir; mkdir -p $T/hermes
    HERMES_HOME=$T/hermes HOME=$T/home hermes plugins install fulcradynamics/fulcra-hermes-plugin --ref <commit> --enable
    scripts/run-desktop.sh <hermes> $T

Put model credentials in `$T/hermes/.env`, without messaging tokens, so the test Hermes can't join your chat channels. On a machine without a display, run it under a virtual one (e.g. `xvfb-run`) with `--no-sandbox --disable-gpu`; `--remote-debugging-port=<port>` lets Playwright attach (`chromium.connectOverCDP`).

In Desktop, turn on the plugin's **Desktop** part (Capabilities > Plugins > Fulcra); **Agents I Know** appears in the sidebar. Desktop's **Install from Git** reviews the repository's default branch even when you pin a commit, so a commit whose Desktop part isn't on that branch installs as agent-only and its Desktop switch shows "copying…"; **Rescan** (on the Plugins toolbar) copies it in. Check each state, running the commands it shows with `HERMES_HOME=$T/hermes HOME=$T/home`:

1. Not added: both commands, each with Copy.
2. After `hermes mcp add` and sign-in: added, with only the `mcp_allowlist` command left.
3. After the grant: the Agents I Know app, once Fulcra answers. Invite someone, reply in a conversation, and use **Continue in Hermes** (it opens a new chat with the request).

## Acceptance

`tests/acceptance/` holds end-to-end scenarios: a real Hermes with the plugin installed, driven turn by turn against test accounts, with a tester playing the user and the contact.
