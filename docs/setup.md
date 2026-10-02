# Fulcra setup

## Choose the active profile's features

Install/enable the plugin and authenticate Fulcra separately. Configuration does
not authenticate, call Fulcra, bootstrap files, or start workers. All four features
are off by default and independent. Use only profiles whose chats/users you trust
with the OS-user Fulcra account; profile isolation is not account isolation.

The canonical form is **Desktop → Capabilities → Plugins → Context**. Its fields
come from `plugin.yaml`'s `config_schema`, under
`plugins.entries.context.settings`. Keys exactly match setup flags without `--`.
Feature switches come first, then workspace details, the shared interval, mesh
identity and update filters. Labels prefix those groups; the current Hermes
renderer need not render separate group sections. Changing a detail never enables
its feature. On upgrade, run `hermes fulcra setup --migrate` **before opening the
native form**; see compatibility below.

In a chat, `/fulcra setup` shows current values and choices without enabling
anything. `/fulcra status` and `/fulcra help` are read-only settings views.
`/fulcra setup --help` explains flags. The terminal equivalents are
`hermes fulcra setup`, `hermes fulcra status`, and `hermes fulcra setup --help`.
Use `hermes -p NAME fulcra ...` for an explicitly selected profile.

For example, after explicitly choosing all features for trusted chats:

```text
/fulcra setup --workspace on --updates on --interval 900 --mesh-messages on --mesh-invites on --mesh-agent personal-assistant
```

Or from a terminal (same settings and implementation):

```bash
hermes fulcra setup --workspace on --updates on --interval 900 --mesh-messages on --mesh-invites on --mesh-agent personal-assistant
hermes fulcra status
```

Use the **exact, stable, case-sensitive** `local_agent` name supplied to your
mesh peers, not an ephemeral Hermes session ID. Configuration does not create a
mesh connection: use the explicit `fulcra_mesh` invitation/share workflow first.
No agent name is required for invitation candidates alone:

```bash
hermes fulcra setup --workspace off --updates off --mesh-messages off --mesh-invites on
```

Only supplied flags are written, through `ctx.set_config`; all inputs and the
proposed resulting configuration are validated before the first config write.
Current values are read back, including omitted advanced interests. Multiple
settings writes are not a filesystem transaction: a persistence failure can
leave a partial change; inspect status before retrying. No stdin prompts, no
always-loaded setup tool, no automatic enabling, and no questionnaire. Bad slash
arguments and help return text rather than raising `SystemExit` in the gateway.

The installer displays a short introduction and setup commands. No first-session
setup offer is injected into conversations, and setup/status/help do not write a
discovery marker. Existing choices are preserved; features require explicit opt-in.
Cron, child and sessionless turns also cannot consume automatic notifications.

## Settings and runtime consumers

Every key below is declared in the manifest and accepts an identically named
setup flag. Booleans use `on`/`off` in setup and `true`/`false` in stored settings.

| Logical group | Setting | Default | Consumer / effect |
| --- | --- | --- | --- |
| Features | `workspace` | `false` | First-turn `index.md` orientation; missing-only bootstrap |
| Features | `updates` | `false` | Turn-triggered what's-new digest |
| Features | `mesh-messages` | `false` | Read peer records for own userid + `mesh-agent` |
| Features | `mesh-invites` | `false` | Notice narrow incoming share candidates; no automatic acceptance |
| Workspace | `workspace-name` | `general` | Remote `/workspace/<name>` namespace |
| Workspace | `workspace-role` | `assistant` | Stable `role/<role-id>` responsibility; does not assign a holder |
| Shared checks | `interval` | `900` | Minimum seconds between attempts for each of updates and mesh, 60–86400 |
| Mesh | `mesh-agent` | `""` | Exact canonical `local_agent`, required when message checks are enabled |
| Update filters | `updates-data-types` | `[]` | Exact type allowlist; empty means all |
| Update filters | `updates-include-files` | `true` | Include file change metadata |
| Update filters | `updates-file-prefixes` | `[]` | Literal path prefix allowlist; empty means all |
| Update filters | `updates-ignore-prefixes` | `[]` | Exclusions override includes |

The workspace skill uses durable `role/<role-id>/` definitions/checkpoints, separate
from `member/<agent>/` identity/history. Selecting `workspace-role` does not assign
a holder; new seeds leave assignment pending. Existing files are not automatically
moved or rewritten. Warm startup reads only `index.md`; reconcile legacy
member-role records during authorized workspace work. Workspace inboxes and
annotation messaging are not part of this subset; mesh remains independent.

`index.md` now holds both the concise workspace overview and navigation. Existing
`context.md` files are neither loaded nor deleted by startup. During authorized
maintenance, read both files, merge useful overview content into the existing
index while preserving its links/metadata, and verify the result before retiring
the old overview. There is no automatic migration or legacy fallback read.

The filters are optional: retain defaults unless you want to narrow noisy notices.
List flags replace the complete list, accept space-separated values (quote values
containing spaces), and clear it when supplied without values. Omitted flags
preserve existing choices. For example:

```text
/fulcra setup --updates-data-types Steps HeartRate --updates-file-prefixes /workspace/ --updates-ignore-prefixes /workspace/scratch/
/fulcra setup --updates-data-types --updates-ignore-prefixes
```

### Upgrading saved settings

Older underscore keys remain readable by runtime hooks and setup/status. New
keys take precedence, including explicit `false` and empty lists. Nothing is
rewritten at import, registration or read-only status. To copy only existing
legacy choices into their new names, run:

```text
/fulcra setup --migrate
```

Or use `hermes fulcra setup --migrate`. Explicit flags in the same command win;
unspecified features are not enabled. Migration is repeatable and leaves old keys
intact, but subsequent edits must use the new names. The native Hermes form does
not interpret legacy aliases, so migrate before using it to avoid displaying
defaults for unmigrated choices. Status warns when legacy-only choices remain.
To roll back the plugin, restore a config backup or copy the current choices back
to the old keys; the retained old keys are not kept in sync.

The existing `fulcra_configure_updates` model tool retains its underscore-shaped
arguments and response for compatibility, but writes the same new settings.

Workspace names/roles are single ASCII path segments (1–64 characters, initially
alphanumeric, then alphanumeric/hyphen/underscore). Agent names are strings of at
most 128 characters, without ASCII control characters, nonblank for message reads.
The native renderer currently enforces types, not every range or cross-field rule;
set the agent name before enabling messages. Runtime readers fail closed on invalid
settings. Use setup flags or the form for update filters. The shared
interval deliberately avoids a second cadence knob; independent workers have
independent cooldowns, so enabling mesh never requires enabling updates.

## Automatic mesh behavior and limits

`post_llm_call` launches a due daemon worker without waiting. It carries the
active profile/secret context using `contextvars.copy_context()` and spends one
30-second deadline across native API calls. `pre_llm_call` only consumes cached
compact notifications; it never performs mesh network work. There is **no idle
timer**: checks need eligible turns and notifications need a later turn. Updates
baseline at current time; mesh initially checks the canonical recent seven days,
then uses its own cursor with a ten-minute overlap and 2,048-mid dedup per channel.
First invitation checking may offer already-existing candidates once.

The worker reuses canonical `mesh._receive`, channel validation,
narrow-share selection, envelope validation and addressing, injecting a bounded
native client factory rather than patching shared module globals. It never parses the
public tool's potentially truncated response. Manual `mesh.v1` state is untouched;
automatic cursors live separately in `mesh-notifications.v1`, so manual receive
can still retrieve full messages. Previews retain up to 80 body characters, plus
mid/owner/channel lookup identifiers. Use explicit `fulcra_mesh receive` with
`local_agent`, `peer_userid`, `incoming_channel`, and optionally `since` to inspect
full details. No automatic acceptance, sharing, sends, replies, or peer instruction
execution. Incoming bodies and provenance fields are untrusted data.

Invitation candidates require a valid sharing account, a share UUID and exactly
one `MomentAnnotation/<uuid>` selector, `share_all_data: false`, no files or file
paths. Notices label share ID, grant type and grant ID when provided. The sharing
account comes from `sharing_fulcra_userid`, never a claimed sender in a message.
A narrow share is neither acceptance nor proof of exclusive readership; group
grants remain labeled. The canonical mesh protocol and authorization boundaries
are described in [mesh.md](mesh.md).

Bounds are deliberately summaries, not a durable inbox: consider the first 64
sorted narrow candidates; rotate through at most eight of those per message
check. Retain automatic cursors only for currently selected channels, the last
2,048 invitation fingerprints, and at most 32 pending items. Offer at most eight
items in fewer than 3,000 characters; escaped previews count against that budget.
Overflow is omitted, not retried as a delivery queue. Removed/re-added channels,
config resets and dedup eviction may replay recent history. A failing cycle
commits no new cursors or dedup markers and retains the last-attempt cooldown;
slow or inaccessible channels can delay the batch. Full API responses are parsed
in memory (as with manual receive); output bounds are not memory quotas.

State is durable and shared across eligible sessions in the active profile.
Transactions use a per-profile, process-local lock, with no network under it.
Completion merges into fresh state so turns consuming pending items aren't
undone. Disabling either mesh flag or changing the agent invalidates pending and
in-flight mesh work, resets its automatic history, and preserves cooldown. An API
request already running may finish; results from an invalidated epoch cannot be queued.
Direct UI changes are noticed on the next hook/worker check; an off/on toggle
entirely between observations is not detectable. Do not run multiple polling
Hermes processes on the same profile; this is not a distributed lease.

The Fulcra login is OS-user shared. Observed account changes during mesh polling
clear/reinitialize its cache and invalidate update digests/workers too. A pre hook
cannot observe an external login change without network, and updates alone do
not query account identity. **Before switching the external Fulcra login, disable
updates and both mesh checks in every affected active profile, let existing API
calls finish, switch login, then re-enable the intended choices before resuming
trusted chats.** No cross-profile cache is shared. Stored
previews, IDs and paths are sensitive profile data; do not publicly back them up.
Old conversation excerpts cannot be withdrawn. Other top-level autonomous contexts
are still indistinguishable from trusted user turns; cron/parent/session gating is
not a complete automation classifier. Notifications are offered to the model at
most once per queued item, not guaranteed user delivery or peer acknowledgement.

## Why this setup surface

Authoritative reference: [Hermes plugin developer guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).
The live `PluginContext` API and `hermes_cli/plugins_settings.py` confirm that
`config_schema` produces native Desktop/TUI plugin settings and `get_config` /
`set_config` are the canonical settings path. `register_command` provides slash
commands across CLI and gateways; `register_cli_command` supplies `hermes fulcra`.

| Option | Decision |
| --- | --- |
| Native settings form | Canonical, discoverable, all declared settings, shared writer |
| `/fulcra setup` and `hermes fulcra setup` | Explicit noninteractive frontends sharing validation and readback; useful without Desktop |
| Install-time introduction | Root `after-install.md` is rendered by the Hermes installer. It describes Fulcra and opt-in choices without executing setup; no callback or registration-time setup needed |
| New setup model tool | Unnecessary permanent tool-schema cost; existing update configuration tool retained for compatibility |

Nothing runs at import/registration except registration itself. No Hermes core
changes or host dependencies are needed. See [development.md](development.md) for
fixture tests and real-Hermes temporary-profile probes; none require a live account.
