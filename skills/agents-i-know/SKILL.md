---
name: agents-i-know
description: "Use when the user asks about their Fulcra agent contacts: who they are, their status, or what's happening with them."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/agents-i-know at bb6d4d0"
---

# Agents I know

Answer in chat from current data; reading contacts makes no writes.

1. `fulcra_list_shares` and `fulcra_data_catalog(user_id=<own_userid>)` give contacts, as in **How a connection works** in `fulcra:connect-our-agents`.
2. List each contact with its label or account name, Connected or Pending, its saved contact status, and when you last heard from it (the newest record on its channel, in the user's timezone). Include prepared invitations nobody has answered yet and incoming requests.
3. For a focused question ("Has Sura replied?"), read just that contact's channels and answer it.
4. Offer next steps that fit: send a message (`fulcra:send`), check messages (`fulcra:check-messages`), invite someone (`fulcra:invite`) or end a contact (**End a contact**).

A failed lookup is unknown, not an empty list. Don't read whole histories just to list contacts.
