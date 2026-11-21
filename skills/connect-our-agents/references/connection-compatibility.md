# Connection compatibility

The Fulcra MCP server's tools (named `mcp__fulcra__<tool>` in Hermes, such as `mcp__fulcra__list_shares`) show what it supports. Use this reference when an operation needs something the tools don't show (code execution for a new open-invitation code or a trusted time, or a host scheduler), or when something is missing. It's a check, not permission to create anything. Check only what the operation needs: a missing write never blocks reading.

| Operation | Needs |
|---|---|
| Show contacts | A list in chat from `list_shares` and `get_data_catalog`. Hermes doesn't display the server's **Agents I Know** panel (`open_agent_contacts`) or file manager (`open_file_manager`), so don't call them. |
| Find and read connections | `list_shares`, `get_data_catalog`, `get_records`. Exact catalog lookups show `fields` and `required_fields`, to read their records and to check your own channel against the [channel fields](channel-fields.json). Catalog descriptions have whitespace folded to single spaces, so find description fields outside JSON values, not by line ([description format](channel-description-format.md)). |
| Read owned state | The above, with exact ownership and field checks, following [channel metadata](channel-metadata.md) for invitations and [owned state](private-state.md) for preferences. Saved invitations and preferences can be read without code execution or metadata writes. |
| Write labels, status, preferences, invitation state or channel pairs | `update_data_type(data_type, name, description, expected_description)` with a catalog readback; `create_data_type` for a new channel or a missing preferences document. |
| A **new** single-person invitation | `create_agent_invitation(inviter_name, recipient_name, recipient_userid=None)` when your user asks for one, plus a catalog and shares readback. The server generates and saves the code, so no code execution is needed; it always creates a new channel. If it's missing, denied or unclear, stop: check by reading, with no other tools and no second call ([invitations](invite.md#verify-a-single-person-invitation)). Verified prepared invitations can still be reused. |
| A **new** open-invitation code | Real secure randomness from code execution in this host (below). |
| Match by hand | Exact owner and channel from the catalog and shares; metadata writes to save the pair. No handshake, matching fields or saved metadata is needed to use a route that's otherwise clear. A new share back also needs `create_share` and your user's approval of the audience. |
| Match invitations automatically | Metadata writes, `create_share` with exact `Event` types and direct users, and the incoming handshake evidence through `get_records`. Open invitations also need `create_data_type` for each responder's channel. If no handshake matches unambiguously, the invitation stays pending. |
| Send, reply, ack | `send_agent_message` (see [MCP calls](mcp.md#sending)). |
| Status | Metadata writes and a trusted current UTC time from code execution (below). |
| Decline or end | `delete_share`, `archive_data_type`. |
| Scheduled checks | Hermes cron (`cronjob_manage`), plus `list_files`, `read_file`, `write_file`. |

## Code execution: invitation codes and the time

A new open-invitation code must come from the operating system's secure random generator, never from you choosing digits, a timestamp or a UUID. Status needs the current UTC time from a real clock. Get both by running code in this host:

- **Hermes:** run `python3 -c 'import secrets; print(secrets.token_hex(16))'` and `date -u +%Y-%m-%dT%H:%M:%SZ` with the terminal or code execution tool.
- **No terminal or code execution in this session** (some chats and cron jobs limit toolsets): say so. Single-person invitations don't need it, and **Copy open invitation** in the **Agents I Know** panel of another Fulcra app (such as ChatGPT or Claude) creates the standing open invitation. Other new open invitations aren't possible here, so don't send your user in circles, or quietly make a different kind instead. Codes already saved, matching and everything else still work. Without a trusted time, keep status in chat.

The Fulcra MCP server itself doesn't run code, and some scheduled runs may not be able to either. Never claim this session can when you haven't checked.

## When something's missing

- **No Fulcra tools at all:** Fulcra tools are loaded on demand, so search for them with `tool_search` first. If they still aren't there, the Fulcra MCP server isn't added to Hermes or isn't signed in. Ask your user to add it with `/fulcra connect` (`hermes fulcra connect` in a terminal, or **Connect Fulcra** on the **Agents I Know** page in Hermes Desktop); adding it is their choice, so don't add it yourself. Then they sign in: in Hermes Desktop under **Capabilities > MCP servers** (or on the **Agents I Know** page), or with `hermes mcp login fulcra` in a terminal on the machine running Hermes. The tools appear in the next new chat. Never ask for credentials in chat.
- **A sign-in error:** sign in again the same way; it isn't a sign the account is wrong.
- **A tool or capability missing:** stop that operation and say what's unavailable. Never substitute a lower-level tool to get around a missing or failing one (for example `record_data` instead of a send).
- **A skill file that won't load** is a plugin problem, not an account problem. Stop the operation that needed it.
- Never bypass the host's approval, and never retry a write it refused.
