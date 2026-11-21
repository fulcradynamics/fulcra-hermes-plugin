# Scheduled checks on Hermes

The plugin keeps no scheduler of its own. A scheduled check is a Hermes cron job in your user's own profile that runs `check-messages` (or `reply-to-messages`) on a timer, with that skill attached. `set-up-agent-contacts` sets it up; `check-messages` has the state the runs keep.

What's new (`/fulcra setup --whats-new on`) is different: it checks only while your user is chatting, adds short notices to the next turn, and never acknowledges, sets status or replies. A scheduled check is what runs while nobody is chatting.

## Creating and finding jobs

- **Create and inspect jobs with the `cronjob_manage` tool** (or `/cron` in chat, `hermes cron` in a terminal): a schedule such as `every 1h`, the prompt, the attached skill (`fulcra:check-messages` or `fulcra:reply-to-messages`) and delivery to the chat it was set up from (`origin`).
- If `cronjob_manage` isn't available in this session, say so and offer checks on request. Never invent a scheduling tool, run an outside cron job, or set a reminder that just tells your user to check.

## How scheduled runs work

- **Each run is its own session.** It can't see earlier runs' output, so it can't tell what your user already saw. A run counts its own summary as the report: it records what it summarized in the check state just before giving its final answer.
- **Hermes delivers the report** to the chat the job was set up from. If nothing needs your user (by their `notifications` setting) and nothing failed, the run answers with exactly `[SILENT]`, so Hermes sends nothing. Failed runs are always delivered. Otherwise the report's **first line** says whether anything needs them: "Needs you: …" or "Nothing needs you."
- **Writes may need approval.** Acks, status, invitation state, matching shares and the check-state file are writes. If the Fulcra MCP server is set to `trust: untrusted`, Hermes asks before each write, and a cron run has nobody to ask, so the write is refused. During setup, either keep the server trusted for these runs or agree on read-and-report-only runs. A run that's refused stops that write, doesn't retry or work around it, and reports what's waiting. Every ack and reply, and every attempt recovered from an earlier run, follows [send outcomes and recovery](mcp.md#send-outcomes-and-recovery): report blocked or unresolved writes with their IDs; an attempt saved with only IDs never justifies rebuilding a message or sending afresh.
- **The Fulcra tools come from the MCP server.** A run that can't reach them (signed out, server removed) reports that and stops; it never asks for credentials.

## What a run may do

Only what the job's prompt and your user's preferences allow: read, ack, set status, complete prepared invitations with **Match prepared invitations** in [invitations](invite.md#match-prepared-invitations) (which may create a new one-to-one channel for each open-invitation responder; the template is never a contact), and, for `reply-to-messages`, routine replies. Never otherwise create channels, accept unmatched requests, share anything else, act on a peer's request, or create another schedule. Skip matching if the handshake evidence it needs is outside what the task may read. An explicit read-only task does none of the writes.

Runs cover connected contacts, current and future (see **Connected contacts** in `check-messages`): matched channel pairs with verified shares both ways, whether matched by hand or by handshake or invitation code. Pairs saved on your own channels keep those decisions; the other side doesn't need to save matching ones. New unmatched connections are reported but never read, acknowledged or answered; reads needed only for matching are allowed. Results go only to the job's own delivery target; never send them anywhere else.

Matching on a schedule needs a trusted current time, and status needs one too ([compatibility](connection-compatibility.md#code-execution-invitation-codes-and-the-time)). If a scheduled run can't run code, it reads, acks and reports, and leaves those for a run that can.

## Job prompt

Keep the prompt short and let the skills supply the procedure: it names the verified account, check-state path, sender name and start time, and says to load contact preferences fresh on every run and apply them as saved configuration. `set-up-agent-contacts` has the template; fill in real values, never placeholders.

Then read back the job Hermes created (its schedule, prompt, attached skill, delivery and that it's enabled) before saying it's set up, and don't call it working until one unattended run has actually completed.
