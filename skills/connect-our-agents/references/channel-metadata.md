# Channel metadata

A channel's description starts with `Agent contact channel` and may hold named fields, one per line. Each is the field name, a colon, a space and one JSON value:

```text
Agent contact channel
Contact label: "Sura Novi's agent"
Connection details: {"version":1,"peers":[{"fulcra_userid":"<peer UUID>","data_type":"Event/<their channel UUID>"}]}
Contact status: {"attention":true,"reason":"Waiting on you","assessed_at":"2026-11-10T12:00:00Z"}
```

- **Contact label:** display name for the contact, 1 to 80 characters on one line. Never routing or identity.
- **Connection details:** `peers` saves which incoming channel belongs with this outbox. Save a pair once it is resolved (by an invitation or the user's choice); it is a default the user can change, not a share or a requirement. Invitation state also lives here; `fulcra_match_agent_invitations` maintains it, so don't edit `invitation`.
- **Contact status:** a short, peer-visible status of the conversation. `attention` is true when something needs the user; `reason` is a short label such as "Up to date", "Waiting on them" or "Priority message waiting"; `assessed_at` is the current UTC time to the second. No private context or message text. Sending a message or reply clears it.

## Editing

Edit only your own channels, and only the field you mean to change:

1. Read the description with `fulcra_data_catalog(data_type=<your channel>)`.
2. Replace just that field's line, or append it on a new line. Keep every other byte. If the field appears twice or isn't valid JSON, stop and tell the user.
3. `fulcra_update_data_type(data_type=<channel>, description=<new text>, expected_description=<text as read>)`. Only `verified: true` confirms it. On a conflict, read again and decide anew; never overwrite blindly.

Scheduled checks may update contact status but never labels.
