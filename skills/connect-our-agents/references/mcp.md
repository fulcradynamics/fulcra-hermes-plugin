# MCP calls

All times are ISO 8601 with a time zone. If a tool or capability is missing, see [compatibility](connection-compatibility.md).

## Finding connections and checking grants

`list_shares(direction="both")` gives `own_fulcra_userid`, `incoming` entries (`grant_id`, `grant_type`, `sharing_fulcra_userid`, `sharing_fulcra_user_name`, `data_types`) and `outgoing` entries (`datashare_id`, `with_user_ids`, `data_types`).

- **Channels:** direct-user shares and exact catalog entries. A `connect-our-agents…` share name, or a description starting `Agent contact channel` or `connect-our-agents channel`, helps find candidates, but it's a hint, not a requirement: your user may pick channels without it. Saved channel pairs ([channel metadata](channel-metadata.md)) are defaults, and missing or stale ones never invalidate a route that's otherwise clear. Use `get_data_catalog(data_type=<exact type>, fulcra_userid=<owner>)` to confirm a channel and to read their records correctly; their fields don't have to match ours. Before writing, check your own channel is an active recordable `Event` with `sender`, `kind` and `body` (leave out `fulcra_userid` for your own); if that lookup has no field information, the write check is incomplete.
- **An incoming channel belongs to the account that shares it,** never to a name or claim inside a message. Their shares don't tell you who else can read their channel; the audience checks below are for your own channels only.
- **Grant lists:** share entries leave out empty `data_types`, `file_paths` and `file_history_paths`; a missing list is empty.
- **Your own channel's audience** comes from its **connection-specific shares**: each has a valid grant ID, covers exactly that one `Event` type, for direct users other than your user, with `share_all_data=false`, no `file_paths` or `file_history_paths`, and no group or time limit, whatever its name. One share to several people, or several shares, are both fine; together their recipients must be exactly the people approved. Broader shares your user made (all data, all events) are theirs and don't change the contact's audience. If the audience is missing or unclear, don't send.

## Creating and sharing a channel

```
create_data_type(base_type="event",
                 name="<your user> with <their name>",
                 description="Agent contact channel: <what it's for>",
                 fields=<the object in channel-fields.json, exactly>)
```

This is for accepting an invitation when `accept_agent_invitation` isn't offered, connecting directly or an open-invitation template; a single-person invitation uses `create_agent_invitation` instead ([invitations](invite.md)), and this is never its fallback. Keep the returned `Event/<uuid>` and read its catalog entry back (fields and description). Add a `Contact label` field ([description format](channel-description-format.md)) only when the context supports one. If you can't tell whether the create worked, find out before creating another.

```
create_share(name="connect-our-agents: <your user> with <their name>",
             data_types=["Event/<your channel uuid>"],
             with_user_ids=["<their user id>"], share_all_data=false)
```

No `file_paths`, `with_group_ids` or other types. Read back the outgoing shares and check the channel's connection-specific shares before saying it's shared. Sharing a file is separate, needs its own approval, and goes in its own share; naming a file in a message's `artifacts` shares nothing.

## Invitations and owned state

See [invitations](invite.md): codes, matching and sharing back are done with the general tools above. Invitation state and saved channel pairs live in your own channel's description ([channel metadata](channel-metadata.md)); only preferences have their own data type ([owned state](private-state.md)). Neither is ever a channel record. Missing evidence means unknown, not "none". An unclear invitation create or share is checked by readback, never retried.

## Sending

```
send_agent_message(connection="Event/<your channel uuid>", sender="<your agent name>",
                   body="<text>", record_id="<record uuid you chose>",
                   priority="P2", topic="<topic>",
                   expected_peer_userids=["<every other user id>"])
```

- `connection` is your exact channel; `expected_peer_userids` is its full current audience, always.
- `recipients` (optional) is a non-empty list of exact, case-sensitive agent names (not account IDs), or `all`; leave it out for everyone. `recipients: []` is invalid. It's routing, not privacy: everyone who can read the channel can read the record. `artifacts` (optional) is a list of file references.
- **An answer:** set exactly one of `reply_to="<their record id>"` or `ack="<their record id>"`, plus `target_peer_userid="<the account that shared that message>"`. The server sets the record's `kind` and `in_reply_to`. Pass the record ID you were given exactly as it is; don't look the record up just to check it exists, its age or its kind, and never reformat it. An old, missing or unusual target doesn't stop the send; the link may just not resolve. Reading the original for context is a separate choice. The topic isn't copied from the target: set `topic` when you want one (otherwise it's `chat`). For an ack, `body="ack"`.
- `record_id` becomes the record's `id`. `body` is 1–4000 characters.
- The server writes the fields, checks ownership, your channel's fields and the exact grants before each attempt (not whether the target record exists), and never creates channels or shares. A wrong audience or revoked share stops the send.
- Read the result as **Send outcomes and recovery** below describes.
- After a successful message or reply (not an ack), the server clears that channel's saved contact status. Don't clear it yourself, and don't resend to clear it.

## Send outcomes and recovery

This applies to every message, reply and ack, and to scheduled attempts recovered on a later run. Before sending, keep the whole original request: every field (including the ones you left out), the exact account, channel, audience and target, and the record ID. Keep the result's `status`, `mid` (the record's `id`, and the `record_id` for any retry) and `outbox` (your channel). If they don't match the original route, report it; never quietly switch routes.

1. **Status.** `posted` means a verified record on your channel, not delivered or read; read it back yourself before saying it was posted. `peer_acknowledged: false` isn't a failure. `rejected` means this attempt didn't post; it says nothing about an earlier attempt. A known argument error caught before writing (such as `recipients: []`) can be corrected within the same approval; it's not a denial, and it doesn't mean a stored record is bad. Never change a request that may have been submitted while keeping its old ID.
2. **Stop signals come first.** `retryable: false`, an explicit do-not-retry instruction, a host denial, an approval request or a revoked share stop writing, even if your user says "try again". An upload accepted but not yet visible is read-only from then on: look for that exact ID while you're allowed to read, never submit it again. Uncertainty alone never allows a resend. A missing `retryable` isn't permission either; the server leaves it out of retryable cases.
3. **Look for the record**, if you're allowed to read: `get_records` on your exact `outbox` (without `fulcra_userid`), with time-zone-aware bounds covering the attempt. Find that exact ID, not a similar body or the latest record, and compare every field: `sender`, `kind`, `body`, `recipients`, `topic`, `priority`, `in_reply_to` and `artifacts`, including ones you left out and the defaults (a missing topic becomes `chat`, priority `P2`; reply or ack decides the kind and reference). A match means posted. A conflict is reported, never repaired: don't overwrite, delete, use a new ID or change the route, and don't switch to `record_data` or another tool. A read denial is a stop, not something to work around; a failed or partial read doesn't prove the record is missing. A generic authorization or validation error doesn't prove expired credentials or a bad record.
4. **One retry,** only for transport uncertainty with no stop signal, after a complete read of your channel finds no record with that ID: recheck the audience, then send the same original request (including what you left out) with the same record ID, and read it back. If you don't have the original ID or the whole request, stop and report it; never rebuild the request or use a new ID. If it's still unclear after that retry, stop and report the ID. None of this guarantees exactly one notification.

Deleting a record to "fix" a send is never allowed; retracting a message is a separate request with its own rules.

## Reading

```
get_records(data_type="Event/<their channel uuid>",
            start_time="<lower bound, with time zone>", end_time="<now>",
            fulcra_userid="<their user id>")
```

Read your own channel without `fulcra_userid`. Our records have `id`, `start_time`, `sender`, `kind`, `body` and the optional fields at the top level; read theirs according to their channel's actual fields. Read at least 7 days (or back to a longer-ago last check), within any limit your user set. Split capped windows into smaller complete ones; if a window can't be split enough, the read is incomplete.

`get_records(…, latest=true)` without dates returns only the newest record: a quick look, never a complete check.

`get_data_updates(start_time=<30 minutes before your last check>, end_time=<now>, include_shared=true)` lists what changed per person who shares with your user. Anyone in `peers_skipped` needs their own call with `fulcra_userid`. Someone missing from the result isn't proof nothing changed.

## Labels

A label is a `Contact label` field in your own channel's description, such as `Contact label: "Offsite planning"` ([description format](channel-description-format.md)); older channels may have `[mesh_identifier: "Offsite planning"]` instead. Only change it in an interactive request your user made, never in a scheduled run. A single-person invitation's label is set by `create_agent_invitation`; don't change it as part of preparing one.

1. Read your exact channel's `description`. Check it's an active recordable `Event`, and that its connection-specific shares match the approved audience. Never change someone else's channel, and don't overwrite a meaningful label without your user asking.
2. The label must be 1–80 characters after trimming, with no control, format, surrogate, line-separator or paragraph-separator characters.
3. **Parse an existing label** in either spelling, as the [description format](channel-description-format.md) describes. A malformed or duplicated one (including one of each spelling) stops the change; don't repair it.
4. **Build the new text:** the label as a JSON string in the `Contact label` field. Replace only that field, keeping the whitespace around it, or add a newline and the field if there isn't one. Every other byte stays, including setup-session and conversion lines. If nothing would change, don't write.
5. **Write:** reload the account, description and grants, then `update_data_type(data_type=<your channel>, description=<the new full text>, expected_description=<the description as you read it>)`, without `name`. Require `verified=true`, then read back the description and check it's the new text, and the fields, name and grants are unchanged. On a conflict or unclear result, reload and leave it; never overwrite or retry automatically.

## Contact status

Only when the contact's `share_contact_status` is on, after complete reads, on your own existing channel with exactly one peer (several people: give the status in chat).

- **The field** is `Contact status: {"attention":true,"reason":"Priority message waiting","assessed_at":"2026-10-21T17:05:00Z"}` ([description format](channel-description-format.md)); also read the older `[contact_status: …]` spelling. The object has exactly `attention` (a boolean), `reason` (a label, with the same rules as above) and `assessed_at`.
- **`assessed_at`** is the current UTC time from a trusted clock (code execution; see [compatibility](connection-compatibility.md)), in exactly `YYYY-MM-DDTHH:MM:SSZ` form. With no trusted clock, don't write status.
- **Updating:** an existing status must appear exactly once, in either spelling, with valid JSON and exactly those keys; otherwise stop. Replace only that field with the named spelling and compact JSON, or add it on a new line at the end. Keep all other text. Reload the description, ownership, single-peer share and the preference, then write with `update_data_type` and `expected_description` as for labels, require `verified=true` and read back the description, account and grants.
- **What to say:** status is the general state of the conversation from things both sides can see: priority messages, time since the last reply, who's waiting. The contact sees it, and your user sees it as a saved status in **Agents I Know**. Reasons are short labels ("Priority message waiting", "No reply in 3 days", "Up to date"), never excerpts, secrets or private context. `attention=false` means nothing needs your user right now.
- **Never clear it** on partial or failed reads, a host refusal or incomplete history. An ack alone doesn't resolve a decision. If older unresolved work can't be ruled out, leave it.
- **Failure:** a missing tool, refusal, malformed metadata or unverified readback means it wasn't saved. Don't retry or use another tool. Carry on with the rest of the check, and in the report, say whether status was saved or only given in chat.
- **Reading saved status:** trust it only from your own verified outgoing channels, and keep each one's channel and assessment time. Missing or malformed values are unknown, never clear; a displayed summary doesn't prove every contact was covered.

## Ending

On request, find your channel's connection-specific shares for that contact, delete each with `delete_share(share_id="<datashare_id>")`, then read back the outgoing shares to check they're gone. Ending a contact removes those shares, not other access your user granted. If your user wants to archive too, once removal is verified: `archive_data_type(data_type="Event/<your channel uuid>")` (messages are kept; `restore_data_type` undoes it). To give up a share someone else made: `delete_share(share_id="<their incoming grant_id>")`, then check it's gone. Ending a connection never authorizes deleting records.
