# Fulcra for Hermes

[Fulcra](https://fulcradynamics.com) gives your agents a place to keep context, work with your data, and collaborate through shared workspaces and explicit sharing.

- **Data and files:** ask Hermes to show your Fulcra data catalog; it will guide sign-in if needed.
- **Workspace context:** `/fulcra setup --workspace on`
- **Data and file notices:** `/fulcra setup --updates on`
- **Mesh message notices:** `/fulcra setup --mesh-agent YOUR_AGENT_NAME --mesh-messages on`
- **Mesh invitation notices:** `/fulcra setup --mesh-invites on`
- **Local literal redaction:** `/fulcra redact help`

Enable the plugin with `hermes plugins enable context` if needed, then start a fresh session (restart the gateway for messaging).

Configure with `/fulcra setup --help`, `hermes fulcra setup --help`, or **Desktop → Capabilities → Plugins → Context**. View settings with `/fulcra status`; replace `on` with `off` to disable features. Workspace and notice features are off by default.

[Setup and account-sharing details](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/setup.md) · [Redaction limits](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/redaction.md)
