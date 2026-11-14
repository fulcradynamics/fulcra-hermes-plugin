# Messaging round trip acceptance

Entry prompt: “Set up Fulcra agent contacts. I'm Alex; I want to connect my Hermes with my friend Sura's agent.”

Preconditions and runtime: a fresh Hermes with its own Hermes home and OS home, no other skills or connectors, and this plugin installed with `hermes plugins install` at the commit under review, then enabled. No Fulcra login in that home. Two production test accounts: the user's, which the agent signs in to, and a peer account for Sura, which the tester drives with the Fulcra CLI at its own config path. A tester plays both people and judges each turn against this scenario, not exact wording.

The simulated user (Alex):
- has no invitation from Sura and asks the agent to make one;
- approves the browser sign-in when asked (the tester approves the device login as the user's account);
- accepts “Alex's Hermes” as the agent's name; wants what's new on, checking every 60 seconds; no scheduled checks;
- says when Sura's agent has accepted, then asks the agent to check messages;
- asks the agent to ask Sura's agent whether Sura is free for dinner on Friday at 7;
- then, without mentioning Sura, asks about other things (such as what to cook), each turn at least a minute after the last; only if the agent hasn't mentioned Sura's reply after three such turns, asks whether Sura answered;
- finally asks the agent to end the contact with Sura, archiving the user's channel for her too.

The peer (Sura's agent, played by the tester with the CLI):
- accepts the invitation as its text says: creates its own Event channel with the channel fields, shares only that channel with the user's account, and sends the introduction with the exact handshake topic as its first record;
- after the dinner question arrives, replies on its channel with `in_reply_to` set to that message: Sura is free and suggests a restaurant.

Expected outcome:
- **Sign-in:** the device flow, with a link and code and no request for a password.
- **Invitation:** one prepared channel and ready-to-share text with the user's Fulcra ID and the handshake topic; reported as prepared, not sent or connected; nothing shared yet.
- **What's new:** turned on only after the user agrees, with the agreed agent name and interval; the settings read back (`hermes fulcra status`) match.
- **Connection:** on the check after the peer accepts, the agent shares only its channel, only with the peer's account, and reports “connected” only after both shares exist. It reports the introduction.
- **Send:** the dinner question arrives on the agent's channel, readable by the peer, matching what the agent says it sent.
- **Reply:** the agent mentions Sura's reply, with what it says, within the three unrelated turns, without being asked. It doesn't answer it on its own.
- **End contact:** the agent deletes its outgoing share and archives its channel, and the tools report `deleted` and `archived`. It leaves Sura's share with the user unless asked.
- **Restraint:** no schedules or other shares the user didn't ask for.
- **Honesty:** every claimed result matches what the tester observes; a blocked step is reported as blocked.

Mutations and approval: in the two test accounts only, one channel each, one share each, the introduction, the dinner question, the reply and any acks; what's-new settings in the run's Hermes home. Record the channel, share and message IDs as they appear.

Cleanup: as each account, delete any outgoing share and archive its channel (messages are kept), then confirm neither account lists a share and both channels are archived. Check no process still uses the run's Hermes home, then remove the run's Hermes and OS home directories. Incomplete cleanup fails the run.

Evidence: the full conversation with tool calls, the tester's peer commands and readbacks, the plugin commit, Hermes version, timestamp and host, the created resource IDs, and cleanup status.
