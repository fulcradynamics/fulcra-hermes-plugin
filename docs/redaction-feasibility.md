# PLAT-480: reversible redaction feasibility

**Status: blocked on host contracts; no redaction feature is installed or implemented.**

[PLAT-480](https://linear.app/fulcradynamics/issue/PLAT-480/add-redaction-of-word-list-with-slash-command)
asks for session/profile private-string lists, stable optional labeled placeholders,
request substitution, output restoration with counts, `/fulcra raw` for one raw
message, and `/fulcra unredact`.

Checked against Hermes source commit `1bb55780ab7be85dee754eaac7b0343ffa560622`
and the [live plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).
The proposed middleware exists, but its current contracts do not suffice for the
full feature with safe failure handling and consistent streamed display.

## Executed reproductions

Run the standalone probe with an **existing provisioned Hermes Python environment**
and its matching source tree. Do not use the `hermes` bootstrap launcher with a
fresh HOME: it may provision a new runtime and rebuild source-tree assets.

```bash
python3 tests/run_redaction_probe.py \
  --python /path/to/existing/hermes/environment/bin/python \
  --source /path/to/hermes-agent
```

The launcher uses disposable HOME/HERMES_HOME/XDG directories under `TMPDIR`,
scrubs inherited credentials, skips plugin discovery, and blocks socket connections
inside the probe. These are protections for a trusted, inspected Python runtime,
not an OS sandbox: site initialization precedes the audit hook, and native code
or subprocesses could bypass it. No such activity occurs in the inspected probe
path. It imports real middleware dispatch and `perform_api_call`;
the provider/stream boundary is a synthetic sink, not a live LLM. It does not
modify installed profiles or source code. Exit 1 means an unmet contract; exit 2
means probe failure; exit 0 means all tested contracts pass. This intentionally
red probe is outside default `test_*.py` discovery. Exceptions are probe errors,
not silently treated as successful privacy protection. If upstream adds a typed
rejection contract, update these probes to recognize that explicit result.

Observed: **three failures, no test errors**:

1. Raising in `llm_request` forwards the original synthetic private user text to
   the provider sink.
2. Raising in `llm_execution` before `next_call` also forwards that text.
3. Execution middleware restores the completed response, but the stream sink has
   already received `{REDACTED-1}`. The probe exercises the real call ordering with
   a synthetic streaming callback; it is not a live-provider or UI test.

These reproduce limitations of a straightforward middleware implementation, not
proof that all conceivable workarounds are impossible. Core source confirms:

- `hermes_cli/middleware.py::_run_execution_chain` logs callback failures and
  continues downstream; request dispatch is also fail-open. The public guide
  explicitly documents this behavior.
- `agent/turn_api_call.py::perform_api_call` wraps the entire
  `_interruptible_streaming_api_call` in execution middleware. Middleware does not
  receive the streaming consumer callback to transform partial placeholders
  before display.

## Additional API gap found by source inspection

`PluginContext.register_command` documents `handler(raw_args) -> str | None`.
`gateway/run_inbound.py` returns the handler result as a handled display response;
`tui_gateway/methods_tools.py::_dispatch_plugin` likewise returns plugin output.
`argument_mode` controls command argument UI, not model-turn submission.
Consequently, simply returning raw text from `/fulcra raw <message>` does not
submit it as a model turn. **`ctx.inject_message` does provide submission**:
it queues CLI input or, with `allow_gateway_injection` consent and a session key,
targets a TUI/desktop/gateway session. Its boolean result means accepted, not
completed. It does not accept immutable per-message bypass metadata. Any design
using it must solve raw-message identity, concurrency, retries and consent rather
than claiming submission is unavailable. This is source inspection, not an
executed cross-surface raw-message test.

Gateway command dispatch binds a source/session **key** before obtaining a
session entry. A session-scoped implementation must prove the mapping to the
middleware's concrete session **ID**, including `/new` and `/resume`; do not infer
it from a process-global last-session variable.

## Narrow host support needed

1. A fail-closed request guard contract whose rejection prevents provider dispatch,
   including errors, retries and fallbacks. Ordinary plugin failure isolation can
   remain fail-open; privacy guards need an explicit different policy.
2. A supported text transformation stage before streaming delivery, with buffering
   across token boundaries and a matching final-response path. It must distinguish
   display content, reasoning, tool arguments, and opaque/signed provider fields.
3. A supported way to attach immutable per-message metadata to session-bound
   submission, extending existing `inject_message` or a command result contract.
   `/fulcra raw` can then use a narrowly scoped bypass marker, rather than arming
   an unsafe “next call” global switch. Existing injection capability alone is not
   evidence that this requirement is impossible; it needs a verified design.

A reduced, explicitly best-effort/non-streaming feature would be a scope change,
not fulfillment of the current issue. No runtime workaround is included here.

## Semantics to settle before implementation

- Adding/changing a list mid-session must not rewrite old cached prompt prefixes.
  Prefer forward-only behavior, with old mappings retained for restoration and
  fresh sessions recommended for material already sent. Redaction cannot retract
  prior disclosure. Whether system/tool content is in scope needs an explicit
  contract; user-text-only substitution is not a blanket privacy guarantee.
- Keep monotonically assigned mappings stable through retries and resume; avoid
  collisions between labels, literal placeholder text, and previous mappings.
  Define literal matching, overlapping phrases, quoting commas/equals, and casing.
- Profile lists and session mappings contain the original private strings. They
  need scoped local storage and clear retention rules, not ordinary config fields
  or logs. Session A → B → A and profile A → B → A tests must cover isolation.
- Human counts must describe actual substitutions without printing the dictionary.
  Model guidance can explain placeholders without revealing their originals.
- `/fulcra unredact` should stop future substitutions without accidentally exposing
  historical private text on replay; `/fulcra raw` must apply only to the explicitly
  submitted message, not other sessions, retries, tool-loop calls or future turns.
- Auxiliary LLMs, compression, logs, stored transcripts and tools are separate
  boundaries; these two middleware hooks alone do not promise coverage of them.

## Existing plugin health

The normal unittest suite remains unchanged. The probes and this note add no
runtime registration, feature flags, dependencies, or partial slash commands.
