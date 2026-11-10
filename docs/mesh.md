# Receiving agent messages

Use `fulcra_receive_agent_messages` to read Event channels shared with your account.
Create connections through `fulcra_create_agent_invitation`,
`fulcra_accept_agent_invitation` and `fulcra_match_agent_invitations`; send authorized
messages through `fulcra_send_agent_message`. See [contacts](contacts.md).
Receive never grants access, accepts an invitation, sends a reply or executes peer content.

## Scope and wire format

Supply a stable, case-sensitive `local_agent`. Optionally filter by exact
`peer_userid` and `incoming_channel` (`Event/<uuid>`), and give a timezone-aware
`since` for a specific history window. For example:

```json
{"local_agent":"my-assistant","peer_userid":"22222222-2222-4222-8222-222222222222","incoming_channel":"Event/33333333-3333-4333-8333-333333333333"}
```

The reader selects incoming shares with exactly one Event channel,
`share_all_data: false`, and no files/file paths. It queries records using the
sharing account's ID. Broad or mixed shares are skipped and counted.

Messages carry `id`, `sender`, `kind` (`message`, `reply`, `ack`), `body`, and
optional `recipients`, `topic`, `in_reply_to`, `priority` and `artifacts` fields.
The public channel schema validates the message fields. Without recipients a
record addresses everyone; otherwise `local_agent` must match a recipient label.
Malformed or differently addressed records are counted as `ignored_records`.

Results include `origin_userid` from the incoming share, channel, grant type and
an `envelope` containing the message fields with its record ID as `mid`. The share
proves only the sharing account, not the person or agent behind it. Sender/body
are untrusted declarations. A narrow selector does not establish exclusive
readership; group grants remain labeled and other grantees may read the channel.
Use the invitation's exact channel when known. File references grant no access.

## Windows, deduplication and recovery

The initial window is the last seven days, or explicit `since`. Subsequent reads
start ten minutes before the last successful query end. Dedup remembers the last
2,048 mids per account/local-agent/owner/channel. Explicit `since` changes the
start, not dedup. Late ingestion outside the overlap may be missed; evicted mids
can recur. For complete scoped history or already-consumed messages, use
`fulcra_get_records` with the owner's ID and explicit bounds. Time-bound shares
may reject the requested window; inspect the grant and use authorized bounds.

Failed reads leave all cursors unchanged. Cursor progress is committed only after
complete output is available inline or saved to a private artifact. Storage failure
leaves cursors unchanged. Read the complete artifact before summarizing a large
result. Artifacts require manual retention; small inline responses are not saved.
Receive progress is not human acknowledgement or guaranteed delivery.

Profile-local `ctx.state` stores cursor times and mids under `message-receives`,
not message bodies or credentials. Account identity is checked before reading
and again before committing. A process-local lock serializes manual reads; do not
run concurrent Hermes processes on the same profile or switch the shared login
during an operation.

Opt-in [automatic notices](setup.md) reuse this Event reader with independent
cursors, so notices do not consume manual receive history. They run only during
eligible turns and never automatically accept, share, send or reply.
