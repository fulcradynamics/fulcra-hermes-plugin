---
name: set-up-agent-contacts
description: "Use when the user wants to set up Fulcra agent contacts or what's new, or to change or stop scheduled message checks."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/set-up-agent-contacts at bb6d4d0"
---

# Set up agent contacts

1. **Sign in.** Call `fulcra_user_info`. If signed out, call `fulcra_auth`, show the user `verification_uri` and `user_code`, and after they approve call `fulcra_auth_device`. Never ask for a password.
2. **Contacts.** List existing contacts briefly, as in `fulcra:agents-i-know`. Then offer: **Invite someone** (`fulcra:invite`), **Accept an invitation** (the invitations reference in `fulcra:connect-our-agents`) or **Skip for now**.
3. **What's new.** Offer to turn on notices of new messages, contact requests and data or file changes during conversations, as in `fulcra:whats-new`. Agree on the agent name used for messages.
4. **Scheduled checks.** What's new only runs while the user is chatting. Offer a scheduled check too: **Check every hour** (`fulcra:check-messages`), **Check and reply every hour** (`fulcra:reply-to-messages`) or **Not now**. Note that checks acknowledge messages and share a general status with contacts, per their preferences.
5. **Create the schedule** only after the user picks one: a Hermes cron job with the chosen skill attached, every hour unless the user picks another interval, delivering to this chat, with the prompt "Check my Fulcra messages as <agent name> for account <own_userid>." Read the job back and report its schedule.

To change or stop checks, find the existing Fulcra cron job, update or remove that one job, and read it back. Never create a second one.

Finish with one line: more Fulcra skills are at https://github.com/fulcradynamics/agent-skills.
