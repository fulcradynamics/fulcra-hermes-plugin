---
name: invite
description: "Use when the user wants to invite someone to connect agents through Fulcra. Creates an invitation to pass on."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/invite at bb6d4d0"
---

# Invite someone

1. Load `fulcra:connect-our-agents` and its invitations reference.
2. Ask only for what's missing: the user's name and the person's name. A named person gets a single-person invitation; otherwise offer one or the user's standing open invitation.
3. Create it once, as in **Create**, and show the invitation text. Say it is ready to pass on, not sent or connected.

The user's request is the go-ahead; don't add a confirmation step or a technical explanation of channels.
