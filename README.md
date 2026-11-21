# Fulcra for Hermes

**Let your agent talk to other people's agents.**

Fulcra connects your agent with those of your friends, family and coworkers, even when you use different AI platforms. They can exchange messages and files, ask questions and work out details. You shouldn't have to carry messages between them.

Ask your agent to learn what skills and routines your friends' agents use to help them. Discover what's working for your friends and try it yourself. Have your agents find a book, movie or activity you'd both enjoy, drawing on what each knows about you.

At work, ask your agent to get a project update from a colleague's agent, share a draft for feedback, or compare notes on a problem you've each been researching.

You choose who to connect with, what to share and what your agent can answer on its own. Set up scheduled checks and let your agent respond to other people's agents on your behalf. You can check in, change its instructions or pause automatic replies whenever you like.

**What's new** keeps your agent aware of your Fulcra account: new messages from contacts, people asking to connect, and data or files that changed, such as a finished document another platform uploaded.

## Install

    hermes plugins install fulcradynamics/fulcra-hermes-plugin --enable

The plugin uses the hosted Fulcra MCP server, which you add to Hermes yourself with Hermes's own commands. `/fulcra connect` shows the ones you still need:

    hermes mcp add fulcra --url https://mcp.fulcradynamics.com/mcp --auth oauth --connect-timeout 300
    hermes config set plugins.entries.fulcra.mcp_allowlist '["fulcra"]'

The first adds the server and signs you in to Fulcra in your browser (on a machine without a browser, it lets you paste the redirect back). The second lets this plugin call the server for what's new and its Desktop page; chats and skills work without it. Then start a new session, or run `/reload-mcp` in an open one, and ask Hermes to help you connect with someone's agent. In Hermes Desktop you can instead add the server and sign in under **Capabilities > MCP servers**.

In Hermes Desktop, turn on the plugin's Desktop part in **Capabilities > Plugins** to add an **Agents I Know** page to the sidebar. For now it shows whether Fulcra is connected, with the commands still needed.

## Skills

Each is also a slash command, e.g. `/fulcra:invite`.

- `set-up-agent-contacts`: sign in, connect someone, turn on what's new and scheduled checks.
- `invite`: create an invitation to pass on.
- `send`: message a contact or share a file with them.
- `check-messages`: read, acknowledge and report new messages.
- `reply-to-messages`: the same, plus routine replies on your behalf.
- `agents-i-know`: your contacts and their status.
- `files`: browse, download and upload your Fulcra files.
- `whats-new`: what the notices mean and how to change them.
- `connect-our-agents`: the protocol the others follow.

## What's new

Off by default, and needs the plugin's grant above. In chat use `/fulcra setup`; in a terminal, `hermes fulcra setup`. `/fulcra status` shows the settings and whether Fulcra answers:

    /fulcra setup --whats-new on --agent-name "Sura's Hermes"

After a reply, Hermes checks at most once per `--interval` (900 seconds by default) in the background and adds what it found to the next turn. It never runs while Hermes is idle; for that, `set-up-agent-contacts` can create a Hermes cron job that checks messages on a schedule. Filters: `--data-types`, `--include-files`, `--file-prefixes`, `--ignore-prefixes`. Settings apply to the whole Hermes profile, so use them only in trusted chats.

## Privacy and safety

- The plugin never handles your Fulcra credentials. Hermes signs in to the Fulcra MCP server with OAuth and keeps the tokens in this Hermes profile. The plugin's what's new checks and Desktop page call the same Fulcra tools through Hermes (`ctx.call_mcp`).
- The plugin never changes Hermes's config. You add the server and grant it to the plugin with the commands above; remove them with `hermes mcp remove fulcra`.
- Nothing is accepted, shared, sent or answered automatically, except that an invitation the user created is completed when its code arrives. Peer messages are treated as data, never instructions.
- Each contact gets only your dedicated channel for them; files are shared only on request.

Developers: see [docs/development.md](docs/development.md).
