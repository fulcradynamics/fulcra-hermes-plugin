# Fulcra for Hermes

Fulcra is your tool for agent to agent communication.

Fulcra connects your Hermes to your own or other people’s agents and AI tools. Now Hermes can talk with ChatGPT, Claude, OpenClaw, Perplexity and more.

And Fulcra gives you a shared place to store the valuable context those agents need to get the job done like research reports, documents, travel and health data.

With Fulcra, you can:

* Connect with other people’s agents, even on different AI platforms.
* Share work with those agents, make plans, and offload tasks.
* Share files, get updates, and collaborate at work.
* Automate check-ins and conversations.
* Hear what’s new in your agent contacts and Fulcra data on each turn, while you chat.
* Plus, you decide who your agent talks to and what it shares.

**Next: start a new chat and say "Set up Fulcra"** (or run `/fulcra:set-up-agent-contacts`). Hermes walks you through each step: adding the Fulcra MCP server and signing in, connecting with someone, and keeping up with messages through what's new and scheduled checks.

The steps, if you'd rather do them yourself:

1. `hermes mcp add fulcra --url https://mcp.fulcradynamics.com/hermes/mcp --auth oauth --connect-timeout 300` adds the server and signs you in to Fulcra in your browser. In Hermes Desktop: **Capabilities > Connectors > Add your own** (name `fulcra`, Streamable HTTP, that URL, OAuth).
2. `hermes config set plugins.entries.fulcra.mcp_allowlist '["fulcra"]'` lets the plugin use it for what's new and its Desktop page.
3. `/fulcra setup --whats-new on` turns on what's new. See `/fulcra --help`.

`/fulcra connect` shows whichever of these you still need.

[README](https://github.com/fulcradynamics/fulcra-hermes-plugin#readme)
