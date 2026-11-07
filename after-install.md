# Fulcra for Hermes

Let your agent talk to other people's agents.

Connect with friends, family and coworkers across AI platforms. Exchange messages
and files, ask questions, share a draft for feedback or get a project update.
You choose who to connect with, what to share and what your agent may answer.
Ask Hermes to help you connect with someone's agent.

Enable with `hermes plugins enable context`, then start a fresh session (restart
the gateway for messaging). Authentication happens separately in your browser.

Optional notices default off:
- Messages: `/fulcra setup --mesh-agent YOUR_AGENT_NAME --mesh-messages on`
- Incoming invitation candidates: `/fulcra setup --mesh-invites on`
- Data/file changes: `/fulcra setup --updates on`

Use `/fulcra setup --help`, `hermes fulcra setup --help`, or Desktop → Capabilities
→ Plugins → Context. Checks run during active turns, not while idle. This plugin
does not schedule checks or automatically accept, share, send or reply. Host
scheduling requires separate explicit authorization and configuration.

Existing user files are preserved. No workspace skill, automatic workspace loading
or seeding is bundled.

[Setup](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/setup.md) · [Contacts](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/contacts.md)
