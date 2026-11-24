# Owned state

Your user's contact preferences are a JSON document stored in the description of a data type in their account, **Fulcra Contact Preferences**. The **Agents I Know** panel uses the same document, so follow this format exactly. It's never put on a contact's channel. Invitations and which channels go together are saved on your own channels instead ([channel metadata](channel-metadata.md)).

## Reading and writing

1. **Find it.** Get your user's ID (`own_fulcra_userid`) from `list_shares(direction="both")`. Look for owned `Event` data types named exactly `Fulcra Contact Preferences`, then read it with `get_data_catalog(data_type=<its exact ID>)` and parse its `description`. It must be your user's and an `Event` type. If there are several, use the one with the lowest ID, as the panel does. Never create a replacement for one that exists but can't be read.
2. **Check it isn't shared on its own:** before using it, and again before each write, look at the outgoing shares. Stop if any grant has `share_all_data=false` and `data_types` exactly `[<its ID>]`, with no `file_paths` or `file_history_paths`, whatever its name. Broader shares your user made (all data, all events) don't stop it.
3. **Parse strictly:** valid JSON with no duplicate keys, the whole document matching the schema below. Keep every other scope and value. Unknown keys, an unknown version or malformed content stops all writes; never repair or drop anything. A missing document means the empty version-1 document, but a failed lookup doesn't mean missing.
4. **Write** only after reloading the account, description and whatever the change depends on. If anything changed, stop and reassess. Merge only the change you're authorized to make.
   - Existing document: `update_data_type(data_type=<its ID>, description=<the complete new JSON>, expected_description=<the description as you read it>)`, without `name`.
   - Missing document: `create_data_type(base_type="event", name="Fulcra Contact Preferences", description=<the JSON>)`, with no `fields`.
   - Then read it back and check the whole document. Never retry a create automatically when its result is unclear.
5. **Races:** `expected_description` only catches a stale read; it isn't a lock. The panel or another run can write at the same time. After every write, check the complete merged document. On a conflict or unclear readback, stop the writes that depend on it, reload and reconcile. Never overwrite someone else's change or claim the write was atomic.

## Preferences

- Root: `version` (1), `global_preferences` (an object) and `overrides`, keyed by `<your channel's Event ID>|<peer's user ID>` with lowercase UUIDs.
- Values contain only the settings in [contact preferences](contact-preferences.md): booleans are real booleans, `unanswered_days` is an integer from 1 to 365, `notifications` is `attention`, `all_messages` or `none`, and `checking_preferences` is a string of up to 2000 characters.
- Restoring a contact to the global values removes that key; it never touches other contacts.

```json
{"version":1,"global_preferences":{"pause_autonomous_replies":true,"notifications":"attention"},"overrides":{"Event/00000000-0000-0000-0000-000000000011|00000000-0000-0000-0000-000000000002":{"unanswered_days":3,"checking_preferences":"Summarize decisions."}}}
```
