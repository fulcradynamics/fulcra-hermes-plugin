# Local literal redaction (PLAT-480)

This is an opt-in main-loop text transformation, not blanket DLP. It uses only
Hermes's official `llm_execution` middleware and `ctx.state`; no core patch,
request hook, stale request/response bridge, or one-message injection is involved.

## Commands

In a supported session:

```text
/fulcra redact add Leif Meyer = user name, Hermes
/fulcra redact list
/fulcra redact remove Leif Meyer, Hermes
/fulcra redact off
/fulcra redact on
```

The first command adds two exact, case-sensitive literal phrases and enables
outbound redaction and completed-text restoration. It produces
`{REDACTED-user name}` and `{REDACTED-2}`. `redact on|off` toggles both together.
`remove` accepts comma-separated exact original phrases in the selected scope,
not aliases or token IDs. Unknown entries reject the whole batch with a generic
error and no changes. Removing the last phrase preserves the scope's on/off state;
adding rules enables it. Removal may expose original historical text next call.
There is no `unredact`, legacy implicit add, `redact status`, top-level `/redact`,
independent restoration setting, `/fulcra raw`, or automatic next-call bypass.
Bare `redact` and `redact help` show help. Add/remove acknowledgements show counts,
not original values.

`list` deliberately displays original phrases and tokens directly to the human,
with the selected scope labeled and inherited profile rules in a separate section.
It never lists other sessions. The verified slash dispatch paths do not invoke an
LLM, append model history, inject a message, or return a model tool result.
This is **not a private channel**: shared chat/history, logs, raw channel-history
ingestion, or someone copying the list into a prompt can expose it later.

Append `--profile` to any command to address the active profile's shared rules:

```text
/fulcra redact add Leif Meyer = user name, Hermes --profile
/fulcra redact list --profile
/fulcra redact off --profile
```

Session rules combine with enabled profile rules. An explicit session `redact
off` overrides both for that session. A profile toggle controls profile rules,
not independent session rules. Session outbound state is tri-state: inherit,
on, or off; profile state is always boolean. Session `redact on`, `redact off`,
or adding session rules sets an explicit override for both outbound
redaction and completed restoration. List/help are read-only: they never create
an override or freeze profile inheritance. Listing includes stored enabled state;
an explicit session off suppresses inherited profile protection too.

Session commands use the supported `get_session_env('HERMES_SESSION_ID')`.
They require a concrete ID, never a global last-session value or a guessed
conversion from a routing key. Gateway command dispatch may supply only a session
key before resolving an ID: **session commands explicitly refuse on that surface**.
Use `--profile` only if you intend to share the rules with every trusted chat in
that profile. Resuming the same concrete ID reuses its rules. Missing execution
identity while rules are active refuses the provider call.

**Conservative session-boundary refusal:** while any session-owned rules remain
enabled in this profile, a concrete ID without an explicit outbound choice refuses
before provider contact, even if profile rules exist. This includes compression
rotation, `/new`, forks, and genuinely unrelated new chats. There is no verified
lineage API or continuation detection. List/help checks do not acknowledge
a new boundary; `redact off` explicitly acknowledges it with protection off.

To acknowledge a new boundary, explicitly run session `/fulcra redact on`,
`/fulcra redact off`, or add session rules. This does **not** copy another session's
rules: `on` enables only this session's own rules plus enabled profile rules, and
`off` allows raw history. After rotation, `on` alone does not restore protection
for phrases owned by the old ID. Review the history/privacy scope before consenting.
Known sessions with explicit `off` retain their override. This availability cost
for unrelated new chats is intentional rather than risking a silent raw resend.

Commas separate phrases; one `=` introduces an optional alias. Leading/trailing
whitespace is trimmed; interior spaces are literal. Quotes have no special meaning.
Literal comma/equal separators are not supported. Aliases use word characters,
spaces and hyphens, begin with a word character, and cannot be purely numeric.
Subcommands are explicit; control words can be phrases after `add` or `remove`.
The reserved `{REDACTED-...}` namespace is rejected in rule values and user input.
Elsewhere only exact tokens allocated in the current effective rules may be
replayed. Unknown or malformed placeholder-shaped text refuses in instructions,
assistant/tool history, JSON tool strings and other text locations; it is never
exempted from protection just because it resembles a placeholder.
Duplicate phrases/aliases and phrases that occur inside any placeholder are
rejected with a generic error and no write. Alias conflicts are checked across
all stored scopes, including disabled rules, to keep mappings unambiguous.
This also rejects the same phrase in two independent sessions. Independent-session
duplicate phrases are not implemented; profile rules are an option only when
intentional sharing with every chat in that profile is appropriate.

Adding an existing phrase is a collision, not a rename. Turning rules
off retains mappings. A profile-local monotonic counter assigns IDs (aliases also
consume an ID); sharing the allocator prevents session/profile collisions and
keeps IDs monotonic in every session. IDs are not recycled and need not start at
1 in each new session. Removal retains only reserved tokens, not deleted originals;
retired aliases cannot bind a new original in any scope of the profile. Stale tokens
in outbound replay are refused while protection is active, never restored to another phrase. Existing
local state without reservations remains valid. Requests never allocate IDs or
upload the dictionary.

## Protection boundary

* All supported outbound message text is covered, not just the latest user text:
  user, assistant, tool, system/developer text, and supported instructions. This
  re-redacts restored names in assistant history before they can be resent.
* Supported text block forms are Chat/Anthropic text, Responses input/output text,
  and Bedrock text. Chat/Responses JSON function arguments and Anthropic tool input
  are parsed, transformed in string values, then serialized safely. JSON property
  names are not renamed; a protected property name refuses the request.
* Role tags, call IDs, tool/function names, schemas, signatures and other protocol
  metadata are never string-substituted. An exact literal found in recognized
  opaque data refuses rather than silently leaking or corrupting it.
* Nonempty SDK `extra_body` overlays refuse: an SDK can merge them after validation
  and replace otherwise-redacted messages. Residual literals are checked after
  substitution and notice insertion, including overlaps at placeholder boundaries.
* Unknown request options, malformed content, unsupported media blocks and
  signed/opaque reasoning replay refuse while active. This intentionally limits
  multimodal and thinking-model workflows. Do not interpret refusal as provider
  failure or as protection for an unsupported payload.
* Structured output is unsupported while outbound protection is on. Chat
  `response_format` with `json_object`/`json_schema` and Responses `text.format`
  structured modes refuse **before provider contact**, including `extra_body`
  overrides. Restoration could break JSON escaping and the completed-text notice
  would violate the format. Omitted format and explicit
  `{"type":"text"}` remain supported. Turning outbound protection off bypasses
  this guard as well as redaction.
* Completed assistant text is restored on a copy. Tool arguments intentionally
  **remain placeholders**, including quotes and backslashes in JSON: no secret
  is injected into a tool action. Tools requiring an original value will not work
  transparently with this mode. Tool names and IDs remain untouched. Reasoning
  text is not restored; signed/opaque reasoning responses are withheld rather
  than risking inconsistent replay.
* Streaming is not rewritten. Placeholders may be visible before completed text
  arrives; stream-is-message surfaces may keep the streamed form. This plugin
  cannot retract a streamed response if completed-response validation fails.
* No transcript/log scrubbing, tool-boundary guard, auxiliary-LLM redaction,
  compression/title/vision protection, or cross-plugin security guarantee is
  claimed. Core request observers, other middleware, logs, saved history, local
  files and auxiliary calls can still see originals. Use trusted plugins only.

With unchanged rules, transformation is deterministic, IDs are stable, and
per-message notices keep historical prefixes stable where possible. Original
history is never mutated in place. Additions, removals and `redact on/off` change
wire history and may invalidate provider caches. Redaction cannot retract text
already disclosed. Start a fresh session when changing the privacy boundary.

The model receives literal-substitution counts and placeholder guidance alongside
supported changed message text, never a raw phrase dictionary. The human receives
outbound and restored counts in the completed assistant text. Counts describe
literal occurrences across the request, including history, not unique phrases or
only the most recent turn. Tool-only completed responses get an assistant notice
without editing the tool call. Only explicit `list` displays the phrase dictionary.

## Failure and storage

Preparation, state reads, validation and redaction are guarded **before**
`next_call`. A failure returns an explicitly local assistant refusal with empty
tools and zero usage, without invoking the provider. Merely raising is unsafe:
Hermes catches before-next middleware exceptions and forwards the original.
Provider exceptions are deliberately outside the guard and propagate once.
Restoration failure withholds the response without retrying the provider; the
provider may already have incurred usage even though the local refusal reports
zero synthetic usage.

Rules and originals live only in the profile-scoped `ctx.state` key
`redaction.v1`, under Hermes's plugin-data directory, not config.yaml or Fulcra.
Hermes writes state atomically with mode 0600. This is local plaintext storage,
not encryption; protect the OS account and backups. Explicit removal deletes the
stored original, not prior chat/history or backups. No automatic expiry or external
upload is implemented. State quotas/errors return generic command
errors; malformed state refuses execution rather than silently disabling privacy.
In-process commands use the existing profile-state lock; use one Hermes process
per profile when changing rules (cross-process read/modify/write is not a plugin
transaction). Disabling/uninstalling the plugin removes its protection, not prior
disclosures or stored originals.

## Offline acceptance

```bash
python3 -m unittest discover -s tests -q
python3 tests/run_redaction_probe.py --python /path/to/provisioned/python --source /path/to/hermes-agent
python3 tests/run_redaction_probe.py --doctor --python /path/to/provisioned/python --source /path/to/hermes-agent
```

The verified local provisioned interpreter was
`/home/fulcra/.hermes/installs/6c5c3c30edc2f176/environments/12d524f9cf7049a7b0579680417b4f8f/venv/bin/python`,
with source `/home/fulcra/.hermes/hermes-agent`.

The launcher uses `-I -B`, disposable HOME/HERMES_HOME/XDG directories under
`TMPDIR`, a scrubbed environment, no installed plugin discovery, and a socket
audit guard. It does not make live LLM calls. Provider responses are synthetic
boundary fixtures; real Hermes middleware, transport builders, `perform_api_call`,
response validation and normalization are exercised. Real CLI `process_command`,
TUI `command.dispatch`/`slash.exec`, and gateway plugin dispatch are also exercised
with model invocation, injection and SessionDB message-append traps. Bootstrap
initialization is stubbed to avoid import-time provisioning; command routes are not.
Chat uses a real OpenAI SDK
response; Anthropic/Responses use protocol-shaped objects and Bedrock uses its
wire dict. The provisioned environment does not include the Anthropic SDK.

If all temporary writes must stay inside the checkout, first create
`.pytest_cache` and set `TMPDIR="$PWD/.pytest_cache"`. Do not set `TMPDIR` directly
to the checkout root for doctor: its copy step would recurse into its own temp
directory. `.pytest_cache` is explicitly excluded by doctor's source-copy step.

`--doctor` calls the exact handler behind `hermes plugins doctor . --ci`. Neither
the bootstrap launcher **nor CLI main** is safe for these disposable-home probes:
CLI main can trigger source-update dependency provisioning. The handler avoids
that startup path. The audit hook is a guard for this inspected Python path, not
an OS sandbox against malicious subprocesses/native code or site initialization.
See [acceptance history](redaction-feasibility.md) for the old findings and the
revised acceptance results.
