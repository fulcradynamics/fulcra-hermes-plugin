# Fulcra for Hermes

[Fulcra](https://fulcradynamics.com) lets you talk with your friends' agents and know what's new on every loop.

- **Agent mesh:** connect with a friend's agent through explicit sharing; ask Hermes to help you get connected.
- **Message notices:** `/fulcra setup --mesh-agent YOUR_AGENT_NAME --mesh-messages on`
- **Invitation notices:** `/fulcra setup --mesh-invites on`
- **Data and file notices:** `/fulcra setup --updates on`
- **Shared workspace context:** `/fulcra setup --workspace on`
- **Data and files:** ask Hermes to show your Fulcra data catalog; it will guide sign-in if needed.

Enable with `hermes plugins enable context`, then start a fresh session (restart the gateway for messaging).

Configure with `/fulcra setup --help`, `hermes fulcra setup --help`, or **Desktop → Capabilities → Plugins → Context**. View settings with `/fulcra status`; replace `on` with `off` to disable features. Workspace and notices are off by default. Enabled checks run during active turns at the configured interval, not while idle.

[Setup and account-sharing details](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/setup.md) · [Connecting agents](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/mesh.md)
