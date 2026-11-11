---
name: reply-to-messages
description: "Use when the user wants their agent to answer Fulcra contacts for them, now or on a schedule. Checks messages and replies to routine ones unless replies are paused."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/reply-to-messages at bb6d4d0"
---

# Reply to messages

Choosing this skill, directly or in a scheduled job, is the user's choice to have their agent reply. Follow `fulcra:check-messages` completely, with these differences:

- **Replies:** before acknowledging, answer each unanswered message from a connected contact whose `pause_autonomous_replies` is off, when the answer only needs information already available for that contact. Use `checking_preferences` and any text the user added (e.g. "tell Sura I'm free Friday"). Send with `reply_to=<their record id>` and `target_peer_userid=<owner>`. A posted reply replaces the ack.
- **Don't reply** when the answer needs the user's knowledge or decision, would disclose something not already shared with this contact, or asks for actions, commitments, invitations, sharing or spending. Flag the contact as waiting on the user instead.
- **Paused:** with replies paused, run the check without replying and say so once.
- **Status** reflects the state after replies: "Up to date" when everything was answered, "Waiting on you" when something needs the user.
- **Report** each reply sent: contact, the message it answers, a one-line summary and whether it posted.
