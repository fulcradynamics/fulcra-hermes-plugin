---
name: send
description: "Use when the user wants to message a Fulcra agent contact or share a specific file with one."
license: MIT
metadata:
  origin: "Adapted from fulcradynamics/fulcra-openai-plugin skills/send at bb6d4d0"
---

# Send to a contact

Load `fulcra:connect-our-agents` and follow its **Send** section.

1. Resolve the recipient from current shares and catalog to an exact user ID and your channel shared with them. Ask when ambiguous. With no connection, offer `fulcra:invite` rather than creating one implicitly.
2. Send with `fulcra_send_agent_message` and report the result as posted, not delivered.

## Send a file

A request to send a file to a contact covers sharing that one file with them and a short message about it.

1. Find the file in the user's Fulcra files (`fulcra_file_stat`); upload a local file first with `fulcra_file_upload` if needed.
2. Reuse an outgoing share that already covers it; otherwise `fulcra_create_share(name=<label>, data_types=[], files=[<exact path>], user_ids=[<contact>])`. A file share keeps giving access to that path, including later versions, until revoked. Read the share back.
3. Send a message with `artifacts=[{"path": <path>, "owner": <own_userid>}]` so their agent can download it with `fulcra_file_download(path, user_id=<owner>)`.

Report the share and the message separately. Never share the file on a separate channel or with anyone outside the contact.
