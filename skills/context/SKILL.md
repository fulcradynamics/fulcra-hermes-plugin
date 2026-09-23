---
name: context
description: Use the pinned CLI-backed Fulcra tools for catalog discovery, records, scoped sharing, updates and files.
---

# Fulcra Context Usage Guidelines

## Discover and authenticate

1. Begin with `fulcra_data_catalog`. Filter by name/category, queryable/recordable,
   base types, owner or API version instead of dumping the entire catalog.
2. On authentication failure, call `fulcra_auth`, show the URL and verification
   code, wait for browser approval, then call `fulcra_auth_device` with the returned
   device code. Never reset auth or run a printed shell command automatically.
3. Credentials belong to the host OS account, shared across Hermes profiles and
   messaging users. The isolated CLI runtime is not account isolation.

## Read and record

- Use exact catalog IDs. `fulcra_data_type_schema` describes writable record fields;
  `fulcra_create_data_type` creates user-defined annotation types, not records.
- `fulcra_get_records` accepts two timezone-aware ISO8601 times, a positive relative
  interval such as `["2 days"]`, or `["latest"]`. Default to a recent relevant
  interval if the user gives none. Translate results to the user's known timezone.
  Raw records can overlap across sources; do not blindly aggregate them.
- `fulcra_record` takes exactly one structured `record` or a `records` array.
  Schema validation stays enabled. Tags may create tags. The CLI adds source
  metadata. `fulcra_delete_records` takes one `record_id`, one `{record_id}` record,
  or a batch of these; never infer bulk deletion scope.
- `fulcra_data_type_lifecycle` consolidates only `archive` and `restore`, with a
  complete `BaseAnnotation/UUID`. It does not delete individual records.
- `fulcra_data_updates` reports processing updates, not event times. Record and
  deletion uploads may be asynchronous: query updates/records before claiming the
  effect is visible. Verify type changes with catalog/schema.

## Sharing

- Read `fulcra_list_shares` with `direction` incoming/outgoing/both first. Incoming
  entries are grants: `fulcra_leave_share` needs an individual `grant_id`, whereas
  `fulcra_update_share` and `fulcra_delete_share` need outgoing share IDs.
- `fulcra_create_share` requires explicit recipients and explicit data/file scope
  OR `share_all:true`. Never infer all-data access. Group recipients include future
  joiners. Missing time bounds are open-ended. Confirm broadening with the user.
- `fulcra_update_share` changes only supplied fields. `set_data_types` replaces
  ALL data/file selectors; `set_files` replaces only file selectors. Empty set
  lists are invalid. `clear` removes selectors and disables all-data sharing before
  additions; `no_group_ids` clears group recipients. Removing bounds broadens access.
- Verify outgoing shares after creating/updating/deleting. Deleting a share revokes
  its grants, not the underlying data. Group grants cannot be left individually.
- Before reading another owner's data, use `fulcra_shared_data_types` with a window
  strictly inside access bounds. `all_data_types:true` plus an empty list means all
  data is shared. Then use that owner's `user_id` on read tools.

## Files

- `fulcra_file_list` and `fulcra_file_stat` return CLI text lines (not invented
  structured metadata). Stat gives your own version history; shared files expose
  only the latest metadata.
- `fulcra_file_upload` takes explicit remote `path` and either literal UTF-8
  `content` or an existing absolute `local_path`. Never select sensitive local files
  without authorization. Existing remote paths gain a new version.
- `fulcra_file_download` returns a bounded UTF-8 preview by default. For binary or
  complete files, provide a NEW absolute `local_path`; existing files/symlinks are
  never overwritten. Remote paths are absolute POSIX paths, without dot segments.
- `fulcra_file_delete` targets one file. Retain stat version IDs if restoration may
  be needed; `fulcra_file_restore` uses `version_id`. Verify changes with stat.
- `fulcra_file_share` preserves the user-only CLI file-share operation. For groups
  or time bounds, use `fulcra_create_share` with `files`. Sharing paths is prefix
  access to latest versions: directories include future files and `/` is all files.
  No version history is implicitly shared. Verify with outgoing shares.

## Output and safety

- Lists default to 200 items/lines and `limit` permits 1–2000. Truncated responses
  include `returned`, `available` and `truncated`; `available` counts this CLI
  response, not a server-wide total. Never describe a truncated response as complete.
- Read tools accept `output_path` to export full parsed JSON to a NEW absolute local
  file, ignoring the display limit. Model output is capped at 24000 characters;
  oversized objects may be omitted with explicit metadata. Narrow queries for large
  datasets because display limits do not limit the server fetch or CLI memory.
- File text previews read at most 12000 bytes; use local downloads for complete
  content. All downloads still fetch the entire file.
- Empty JSONL streams mean no rows. Empty successful text mutation output is not a
  subprocess failure; do not invent IDs/counts. Nonzero exits are errors. Error
  details are intentionally redacted to avoid leaking credentials.
- Mutating tools need the user's intended target and scope. A CLI success is not
  read-back verification: use the relevant read tool before claiming completion.
  Do not blindly retry writes after timeouts; check whether the effect occurred.
- These are fixed-operation tools, not a generic CLI runner. Do not add arbitrary
  options, disable validation, repair malformed identifiers or bypass rejected args.
  Keep summaries concise and grounded in returned data.
