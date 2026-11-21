---
name: files
description: Move files between Hermes and the user's Fulcra account, or browse what's there. Use when the user asks to upload, download, save, browse or share a file in Fulcra, or wants a file Hermes made (a spreadsheet, PDF, image, report or data export) kept in Fulcra.
---

# Fulcra files

The user's Fulcra account keeps files of any type, with every version kept. Use the Fulcra MCP server's tools (`mcp__fulcra__read_file`, `mcp__fulcra__write_file`, `mcp__fulcra__list_files` and so on). Paths are absolute and start with `/`, such as `/reports/q3.xlsx`. Don't confuse them with Hermes's own file tools, which work on this machine.

## Before you start

If the Fulcra tools aren't there after a `tool_search`, the Fulcra MCP server isn't connected or signed in. Tell the user how to connect it ([compatibility](../connect-our-agents/references/connection-compatibility.md#when-somethings-missing)). Don't try another way. Hermes doesn't display the Fulcra file manager panel, so don't call `open_file_manager`.

## Browse

`list_files(path)` lists a folder; show the user what's relevant, not every entry of a large folder. To browse files another user shares with them, pass that user's Fulcra ID as `fulcra_userid`; that view is read-only.

## Save a file to Fulcra

Pick by where the file is and how big it is. After saving, tell the user the path.

- **Text you wrote** (notes, JSON, CSV, Markdown): `write_file(path, content)`.
- **A binary file on this machine up to 5 MB** (a spreadsheet, PDF or image, including one the user points to): base64-encode it with the terminal or code execution tool, then `write_file(path, content=<base64>, encoding="base64")`.
- **A file on this machine over 5 MB, up to 30 MB:** call `write_file(path, encoding="upload_link")`. It returns a link and a command; run it with the terminal tool: `curl -sS -T <file> '<link>'`. The link works once, for 10 minutes.
- **Over 30 MB, or a file on another computer:** Hermes can't upload it. The user can upload it from another Fulcra app's file manager (ChatGPT or Claude) or the Fulcra web app.

Only read files on this machine the user asked you to save. Never paste base64 into the conversation for the user, and never print a whole file to save it.

A new file can take a few seconds to show up in `list_files`. If it isn't there yet, wait briefly and check again before saying it failed.

## Get a file from Fulcra

- **To this machine:** `read_file(path, as_link=true)` returns a link that works for 10 minutes; download it with the terminal tool (`curl -sS -o <local path> '<link>'`) to the place the user named, and tell them where it is.
- **For the user to download:** give them the link from `read_file(path, as_link=true)` and say when it expires.
- **To read it yourself:** `read_file(path)`. Spreadsheets (`.xlsx`) come back as CSV, one section per sheet. Large files are cut off at `max_bytes`; raise it only when you need the whole file.
- **A file another user shares:** pass their Fulcra ID as `fulcra_userid`.
- **To someone's agent:** to send a file to a person the user is connected with through Fulcra, use the `send` skill. Browsing or saving a file never shares it.

## Other file tasks

- **Delete:** `delete_file(path)`, only when the user asks. Earlier versions are kept, so it can be undone.
- **Earlier versions:** writing to an existing path makes a new version. To bring one back, find its ID with `list_files(path, include_versions=true)`, then call `restore_file(version_id)`.
