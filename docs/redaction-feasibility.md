# PLAT-480 acceptance and retained host limits

Implemented under the revised scope: official plugin APIs only, fail closed,
completed-response restoration, and explicit slash toggles instead of `/fulcra raw`.
See [redaction.md](redaction.md) for commands and privacy boundaries.

## Host contracts

Probes against Hermes `1bb55780ab7be85dee754eaac7b0343ffa560622` established:

- Request middleware exceptions and execution middleware exceptions before
  `next_call` can forward the original request. Raising is not a privacy guard.
- Execution middleware receives the completed response after streaming delivery.
- Slash-command returns are display text, never `inject_message`, context hooks,
  or model tool results. The follow-up uses explicit add/remove/list and retains
  on/off; no unredact or top-level redact alias is registered.
- Gateway command handlers can receive a routing key without a concrete ID.
  Compression can rotate concrete IDs without a verified plugin lineage contract.

One `llm_execution` middleware now owns preparation and restoration. Local
preparation failures return a supported, explicitly local refusal **without
calling next_call**. Provider errors propagate once; restoration failures withhold
the completed response without retrying. Streaming remains unchanged.

Key-only commands refuse session scope. Unknown execution identities refuse while
session-owned rules remain active, including unrelated new chats. Explicit session
commands acknowledge a new boundary, without copying another session's rules.
These restrictions are intentional fail-closed behavior, not lineage inference.

## Verification

- `python3 -m unittest discover -s tests -q`: **82 tests, OK, 2 existing skips**.
- Real-Hermes offline acceptance: **18 tests, PASS**.
- Isolated plugin doctor command handler: **PASS**, 25 tools and 7 hooks.
  Existing `keywords`, `provides_commands`, and `repository` manifest warnings remain.
- `git diff --check`: pass. No installed Hermes core changes or live-profile installation.

Tests exercise real middleware dispatch, `perform_api_call`, four transport builders
and response parsers, A→B→A profile isolation, coupled toggles, immutable history,
zero-provider-call refusal, one-call provider failures, and completed/stream ordering.
Regression tests were observed failing before fixes for unknown placeholders,
implicit off overrides, rotated identities, structured output, SDK body overrides,
and overlapping literals at placeholder boundaries.
The follow-up observed failing add/list and removal/retired-token regressions
before implementation. Exact-original removal is atomic and scope-local, keeps
the toggle and monotonic counter, and reserves deleted tokens without retaining
deleted originals. Older state without reservations remains valid.

Real CLI `process_command`, TUI `command.dispatch` and `slash.exec`, and messaging
gateway plugin dispatch display list output without model invocation, injection,
or SessionDB message appends. CLI/TUI model-history fixtures remain unchanged.
TUI binds the live agent's session ID; key-only messaging gateway session commands
refuse and explicit profile listing works. This does not prove that external raw
channel-history ingestion, logs, or later copied output cannot reach a model.

These are **offline tests with synthetic provider boundaries**, not live LLM/UI
calls. Chat uses an OpenAI SDK response; Anthropic/Responses fixtures are
protocol-shaped objects, and Bedrock uses a wire dict. The provisioned environment
lacks the Anthropic SDK; it was not modified to install it.

The runner uses an already provisioned interpreter, isolated imports, disposable
homes and a Python socket audit guard. Importing CLI initially attempted package
provisioning; the audit guard blocked it. The harness now stubs bootstrap only,
leaving actual dispatch intact, and passes without provisioning attempts.
Invoke the doctor handler directly: both
the bootstrap and CLI main can trigger provisioning under a fresh HOME. Keep
temporary directories outside the source checkout, or inside doctor-excluded
`.pytest_cache`, to avoid recursively copying the source into itself.

## Boundaries

This is main-loop literal text protection, **not blanket DLP**. Auxiliary models,
compression/title calls, logs/transcripts, tools and other plugins remain outside
its guard. Streaming and tool arguments retain placeholders. Unsupported media,
signed reasoning, structured output, nonempty SDK body overlays and unknown
payloads refuse while enabled. Listing exposes originals in shared chat/history;
it is not guaranteed private. Removal or turning off can resend original history;
rule/toggle changes can invalidate caches. Rules persist as local plaintext in
profile-scoped `ctx.state`. Full details are in [redaction.md](redaction.md).
