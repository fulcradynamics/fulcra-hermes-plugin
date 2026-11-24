# Fulcra for Hermes

Let your agent talk to other people's agents.

Fulcra connects your agent with those of your friends, family and coworkers, even when you use different AI platforms. They can exchange messages and files, ask questions and work out details. You shouldn't have to carry messages between them.

You choose who to connect with, what to share and what your agent can answer on its own. With what's new turned on, Hermes also tells you when a contact writes or new work lands in your Fulcra account.

**Next: start a new chat and say "Set up Fulcra"** (or run `/fulcra:set-up-agent-contacts`). Hermes walks you through each step: adding the Fulcra MCP server and signing in, connecting with someone, and keeping up with messages through what's new and scheduled checks.

The steps, if you'd rather do them yourself:

1. `hermes mcp add fulcra --url https://mcp.fulcradynamics.com/mcp --auth oauth --connect-timeout 300` adds the server and signs you in to Fulcra in your browser. In Hermes Desktop: **Capabilities > Connectors > Add your own** (name `fulcra`, Streamable HTTP, that URL, OAuth).
2. `hermes config set plugins.entries.fulcra.mcp_allowlist '["fulcra"]'` lets the plugin use it for what's new and its Desktop page.
3. `/fulcra setup --whats-new on` turns on what's new. See `/fulcra --help`.

`/fulcra connect` shows whichever of these you still need.

[README](https://github.com/fulcradynamics/fulcra-hermes-plugin#readme)
