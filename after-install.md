# Fulcra for Hermes

[Fulcra](https://fulcradynamics.com) gives your agents a place to keep context,
work with your data, and collaborate through shared workspaces and explicit
sharing. This plugin connects Hermes to your Fulcra account.

## Get started

If you installed with `--no-enable`, run `hermes plugins enable context`.
Start a fresh Hermes session; for messaging platforms, restart the gateway to
load the plugin. API calls run natively in Python; no Fulcra CLI or uv is needed.

Ask Hermes: **“Show me my Fulcra data catalog.”** If you aren't signed in,
Hermes provides a verification link and code. Sign-in is separate from setup.
You can then ask Hermes to read or write records, manage files, or share specific
data with people you choose. Sharing requires explicit recipients and scope.

## Choose your features

Open **Desktop → Capabilities → Plugins → Context**, or run `/fulcra setup`
in chat (`hermes fulcra setup` in a terminal) to see your current choices.
Setup with no flags doesn't enable anything. These four features are independent
and **off by default**; enable only the ones you want:

- **Workspace context:** carry preferences and project knowledge into future
  sessions by loading your workspace's `context.md`.
  `/fulcra setup --workspace on`
  Defaults to workspace `general`, role `assistant`; when the entrypoint is
  missing, enabling this also allows creation of missing workspace starter files.
- **What's-new notices:** surface changes to your Fulcra data and files.
  `/fulcra setup --updates on --interval 900`
  The shared check interval is in seconds; narrow your interests in Desktop settings.
- **Mesh message notices:** check messages addressed to your agent from connected
  Fulcra accounts.
  `/fulcra setup --mesh-agent personal-assistant --mesh-messages on`
  Replace `personal-assistant` with the exact stable agent name your peers address;
  ask Hermes to set up the mesh connection separately.
- **Mesh invitation notices:** discover incoming sharing invitations without
  automatically accepting them.
  `/fulcra setup --mesh-invites on`
  This works independently of message checks and needs no agent name.

Use the same flags with `hermes fulcra setup` in a terminal. Replace `on` with
`off` to disable a feature; `/fulcra status` shows your choices. Update and mesh
checks run after active turns when due, with notices available on later turns—not
while Hermes is idle. They never automatically accept invitations, share back,
send replies, or execute peer instructions.

**Use only with trusted chats.** Feature choices apply to the whole Hermes
profile. Fulcra sign-in is shared by Hermes profiles and users running under the
same OS account; profiles do not isolate Fulcra accounts.

You can configure this later. The existing one-time first-session setup reminder
remains available if you haven't handled setup yet.

For optional local literal redaction, start with `/fulcra redact help`.
`/fulcra redact add Leif Meyer = user name, Hermes` adds session rules without a
Fulcra upload. Use `redact remove` with exact phrases, `redact list` to display
phrases/tokens, and `redact on|off` to toggle protection. Lists appear directly to
the human, not the model, but shared chat/history is not guaranteed private.
Removing rules may expose original history next call.
Streaming placeholders may remain visible; this is not blanket
protection for tools, logs, transcripts or auxiliary models. See
[redaction and limits](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/redaction.md)
before using `--profile` or turning protection off.

[Setup details](https://github.com/fulcradynamics/fulcra-hermes-plugin/blob/main/docs/setup.md)
