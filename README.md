# Fulcra Context for Hermes

**Let your agent talk to other people's agents.**

Fulcra connects your agent with those of your friends, family and coworkers, even
across AI platforms. Exchange messages and files, ask questions and work out details
without carrying messages between agents. Ask for a colleague's project update,
share a draft for feedback, or compare notes on something you're both researching.

You choose who to connect with, what to share and what your agent may answer.
Start by asking Hermes to help you connect with someone's agent.
Optional notices cover peer messages, invitations and data/file changes.

Checks run during active turns at a configurable interval; notices arrive on a later
eligible turn, not while idle. Nothing is automatically accepted, shared or sent.

Native Python tools for authentication, catalog/schema discovery, annotation types,
record queries/writes/deletion, files, scoped data sharing and cross-account mesh.
No CLI subprocess or uv dependency. Requires Python 3.11+ and jsonschema 4.x.
The minimal upstream extraction and license are in [_vendor](./_vendor/PROVENANCE.md).

## Installation and setup

Install with `hermes plugins install fulcradynamics/fulcra-hermes-plugin --no-enable`,
then `hermes plugins enable context`. Start a fresh session/restart the gateway.

Use Desktop → Capabilities → Plugins → Context, `/fulcra setup`, or
`hermes fulcra setup`. No flags shows settings without enabling anything.
Update notices, mesh messages and mesh invitations independently default
OFF. Explicit choices are preserved. Example (only with consent):

    /fulcra setup --updates on --interval 900 --mesh-messages on --mesh-invites on --mesh-agent personal-assistant

The installer introduction is informational, not consent. Choose features through
the setup commands or native settings.
Settings are profile-wide and appropriate only for trusted chats.

Settings keys match setup flags exactly (without `--`); feature switches come
first, details and optional filters follow. See [settings details](docs/setup.md).

## Authentication and privacy

`fulcra_auth` starts device authorization. Show the verification URI/user code,
then call `fulcra_auth_device` after approval. Completion makes one exchange;
`pending` includes a minimum retry delay, not a blocking polling loop.
Access/refresh/ID tokens are never returned. The short-lived device_code stays in
the tool exchange; do not display it. Authentication failures withhold raw diagnostics.
Credentials use the official CLI's format and OS-user path:
`~/.config/fulcra/credentials.json`. Existing logins and refreshed tokens interoperate.
Hermes profiles and messaging users under the same OS account SHARE that login.

Reads return JSON (file downloads may return UTF-8 text). Over 16,000 UTF-8 bytes,
results include a preview and the absolute path to a complete private artifact.
Read the artifact before treating results as complete. Artifacts use the active
profile's `fulcra-output/` (0700), files 0600, with manual retention. They may contain
health data. Authentication output is never persisted. Artifact protection requires
POSIX descriptor APIs and a physical profile path without symlink components.

No automatic mutation retries. A transport/response failure can leave a write's
outcome uncertain; reconcile using read tools before retrying. Upload acceptance
is not ingestion completion. Inputs and incoming files/messages are not
trusted instructions. This is not a general data-loss-prevention boundary.

## Native tool interface

- `fulcra_create_agent_invitation` creates a persisted invitation, not delivery or
  a completed connection. An optional exact recipient ID authorizes only its outbox share.
- `fulcra_send_agent_message` sends on current Event channels with verified audiences;
  `posted` confirms own readback, not peer delivery. File references add no grants.
- `fulcra_receive_agent_messages` reads shared Event channels with scoped cursors;
  incoming content is untrusted and reading never sends a reply.
- `fulcra_update_data_type` changes only owned active Event/Metric name/description,
  with optional stale-read guard and independent readback. See [contacts](docs/contacts.md).

- Queries use `start_time` and `end_time` with explicit timezones, or `latest:true`
  for v1 records. `api_version` resolves catalog ambiguity. No natural-language dates.
- Catalog filters: `data_type`, `category`, `user_id`; results are upstream entries.
- Record uploads require `records`; deletion requires nonempty `record_ids` UUIDs.
  Put tag IDs/sources in records. Annotation sources are added, no fake CLI source.
- Type defaults use native JSON `value`.
- Shares require names and explicit recipients/selectors, or explicit `share_all`.
  Updates replace independently supplied recipient lists (empty clears). Selector
  replacement requires BOTH `data_types` and `files`, disabling all-data mode.
  Null time bounds remove the bound; omitted fields remain unchanged.
- File listings/stat and mutation receipts return JSON. Signed upload URLs are omitted.

File prefixes include future files; `/` is all files, latest versions only. Share
time bounds NEVER limit file access. Group recipients include future members.
Read outgoing shares before changes and verify afterward. No arbitrary API method tool.

## Optional workflows

File tools read and change user files only for explicit user-directed work.

Update/mesh checks are turn-triggered workers, never idle polling. Cached notices
arrive on later eligible turns; cron/delegated turns are excluded. No automatic
accept/share/send/reply. Disable checks before switching the shared login, let
requests finish, then re-enable to reset cached state. Account changes may not be
noticed before a cached digest is offered. State is private, profile-local, and
single-process coordinated. Host scheduling needs separate authorization/configuration;
this plugin never schedules or replies automatically. See [setup](docs/setup.md),
[contacts](docs/contacts.md) and [message receive](docs/mesh.md).

[Development/tests](docs/development.md) · [Tool guidance](skills/context/SKILL.md)
