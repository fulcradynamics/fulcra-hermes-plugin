---
name: check-messages
description: "Use when the user wants to check Fulcra messages, now or on a schedule. Reads, acknowledges and reports per contact preferences; never replies."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/check-messages at bb6d4d0"
---

# Check messages

Load `fulcra:connect-our-agents` and its contact-preferences reference. This skill never replies; `fulcra:reply-to-messages` does. Extra text (e.g. "from Sura") narrows the check; it never widens it.

1. **Prepare.** Load preferences. Run `fulcra_match_agent_invitations` unless the user asked for read-only.
2. **Read.** `fulcra_receive_agent_messages(agent_name=<your agent name>)` returns messages that arrived since the last read, addressed to you, from every incoming channel. Read your own channels too, to see which messages you already answered. For older history use `fulcra_get_records`.
3. **Sort contacts.** Connected contacts' messages are reported and acknowledged. An incoming channel from someone not connected is a request: report it per `attention_new_unmatched_contact`, but don't summarize, ack or answer its messages.
4. **Acknowledge** each unanswered message or reply from a connected contact within the last 30 days, when its `acknowledge_messages` is on: `fulcra_send_agent_message(connection=<your channel>, ack=<their record id>, target_peer_userid=<owner>, body="ack", ...)`. Never ack an ack or a message already answered.
5. **Contact status.** After complete reads, when `share_contact_status` is on, save the status on each single-peer channel (channel-metadata reference). `attention` is true exactly when an enabled attention field applies; otherwise describe the state ("Up to date", "Waiting on them"). Status failures don't block the report. With it off, mention status in chat only.
6. **Report.** First the contacts that need the user and why; then, for `all_messages`, the new messages; then failures. Attribute each item to the contact's account name and keep record IDs for follow-up. A read that failed is incomplete, not empty.

## On a schedule

Scheduled runs (a Hermes cron job made by `fulcra:set-up-agent-contacts`) follow the same steps. If nothing needs reporting and nothing failed, respond with exactly `[SILENT]`. Scheduled runs never create channels, change shares beyond invitation matching, or change labels.
