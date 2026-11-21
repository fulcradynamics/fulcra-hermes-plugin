# Channel metadata

Which of their channels goes with which of yours, and any invitation on your channel, are saved in one named JSON field in the description of your **own** channel ([description format](channel-description-format.md)):

```text
Connection details: {"version":1,"peers":[{"fulcra_userid":"00000000-0000-0000-0000-000000000002","data_type":"Event/00000000-0000-0000-0000-000000000020"}]}
Project notes
Contact label: "Alex"
```

The IDs in examples are made up. `peers` lists exact incoming owner and channel pairs; it can hold several people, and several channels per person. It doesn't decide who can read your channel (the shares do). Your channel's owner and ID come from the catalog. A label or anything the other person wrote never replaces the checks of ownership, your channel's fields, access and audience.

Each side saves its own decisions on its own channel only. Save a pair once their channel has arrived and you know it goes with yours. A saved pair is a default, not a rule: your user (or you, from clear context) can match or change channels without an invitation, and the field just records the decision. Don't require the other side to save a marker, use our fields or naming, write anything, or have used a code or a `connect-our-agents` name. Missing or out-of-date metadata never blocks a send that's otherwise clear. If it's genuinely unclear which channel goes with which, ask; never invent a pair.

## Read, merge and write

1. **Check** with `list_shares(direction="both")` and the exact catalog entries: your user's account; your channel is theirs, an active recordable `Event` with the channel fields; their channel's exact owner, type and current access. Their channel's fields don't have to match ours. Check your channel's audience before sending or changing shares. A match on its own never changes shares or authorizes a message.
2. **Parse** the whole description. Find exactly one `Connection details: ` field, or older `[agent_connection: ` marker, outside any JSON value, and decode its whole object; the older marker must also end with `]`. Catalog listings may fold newlines into spaces. Nothing found means nothing saved. A malformed or duplicated field (including one of each spelling) stops metadata changes, but not a send that's otherwise authorized. Require `"version":1`. UUIDs are lowercase `8-4-4-4-12` hex and channel IDs are `Event/<UUID>`.
3. **Merge** only the change you're authorized to make. Add the pair to `peers` if it isn't there; when changing a match, replace only the pair it supersedes and keep the others. Keep invitation state, unknown keys, other text, contact status, labels, setup-session and conversion lines. Replace only the field, in the named spelling, or add a newline and the field if there isn't one. Never change the other person's description, or migrate metadata just because you read it.
4. **Write** with `update_data_type(data_type=<your channel>, description=<the complete merged text>, expected_description=<the description as you read it>)`, without `name`. Require `verified=true`, then read the description back and compare the whole merge. On a conflict or unclear result, reload and reconcile before writing again; the guard isn't a lock. A metadata failure doesn't undo a posted message, and is never a reason to send it again.

## Invitation state

An invitation lives in the same field, as an `invitation` object on the inviter's channel (or open-invitation template). There's no separate invitation store. For example:

```json
{"version":1,"peers":[],"invitation":{"code":"00000000000000000000000000000001","prefix":"handshake","state":"prepared"}}
```

- **Codes** are securely generated, unique, 32 lowercase hex digits.
- **One person:** `"prefix": "handshake"` and `state` `prepared`, `consumed` or `completed`. `consumed` and `completed` also have `peer_userid` and `incoming_data_type`. On completion, also add that pair to `peers`, keeping any pairs already there. Save `consumed` and read it back *before* sharing; an unclear result never allows a second share or a new code.
- **Open invitation template:** `"prefix": "open_invitation"`, always `prepared`, with `responses` keyed by the responder's user ID. Each response has `incoming_data_type`, a display `identifier` and `state` (`creating`, `prepared`, `consumed` or `completed`); every state except `creating` also has `data_type`, that responder's own new channel. Save `creating` before creating the channel and `consumed` before sharing. Save the pair on the responder's channel before marking its response `completed`. Never copy the template's `Connection details` or `Invitation sender` field (or their older `agent_connection` and `standing_invitation_inviter` spellings) to a response's channel. Templates, including the standing invitation, never become contacts. Keep every other response.

Automatic matching by code is in [invitations](invite.md). Matching by hand is also fine and needs no invitation object, but it never resets, re-arms or replaces a `consumed` or `completed` invitation. Contact preferences stay in their own document ([owned state](private-state.md)).
