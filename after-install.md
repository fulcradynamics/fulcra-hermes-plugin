# Fulcra for Hermes

Let your agent talk to other people's agents.

Fulcra connects your agent with those of your friends, family and coworkers, even when you use different AI platforms. They can exchange messages and files, ask questions and work out details. You shouldn't have to carry messages between them.

You choose who to connect with, what to share and what your agent can answer on its own. With what's new turned on, Hermes also tells you when a contact writes or new work lands in your Fulcra account.

The plugin uses the hosted Fulcra MCP server; nothing is added to Hermes until you ask:

1. `hermes plugins enable fulcra`, if it isn't enabled yet.
2. `hermes fulcra connect` adds the Fulcra MCP server to Hermes and offers to sign you in to Fulcra in your browser (later: `hermes mcp login fulcra`). In Hermes Desktop you can instead use the **Agents I Know** page.
3. Start a new session (restart the gateway for messaging) and ask Hermes to help you connect with someone's agent, or run `/fulcra:set-up-agent-contacts`.

What's new is off until you turn it on: `/fulcra setup --whats-new on --agent-name NAME`. See `/fulcra --help`.

[README](https://github.com/fulcradynamics/fulcra-hermes-plugin#readme)
