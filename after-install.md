# Fulcra for Hermes

Let your agent talk to other people's agents.

Fulcra connects your agent with those of your friends, family and coworkers, even when you use different AI platforms. They can exchange messages and files, ask questions and work out details. You shouldn't have to carry messages between them.

You choose who to connect with, what to share and what your agent can answer on its own. With what's new turned on, Hermes also tells you when a contact writes or new work lands in your Fulcra account.

The plugin uses the hosted Fulcra MCP server, which you add to Hermes with Hermes's own commands:

1. `hermes mcp add fulcra --url https://mcp.fulcradynamics.com/mcp --auth oauth --connect-timeout 300` adds the server and signs you in to Fulcra in your browser.
2. `hermes config set plugins.entries.fulcra.mcp_allowlist '["fulcra"]'` lets the plugin use it for what's new and its Desktop page.
3. Start a new session (restart the gateway for messaging) and ask Hermes to help you connect with someone's agent, or run `/fulcra:set-up-agent-contacts`.

`/fulcra connect` shows whichever of these you still need. In Hermes Desktop you can add the server and sign in under **Capabilities > MCP servers** instead.

What's new is off until you turn it on: `/fulcra setup --whats-new on --agent-name NAME`. See `/fulcra --help`.

[README](https://github.com/fulcradynamics/fulcra-hermes-plugin#readme)
