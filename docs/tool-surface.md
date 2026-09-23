# Tool surface expansion

## Agreed design

Keep the plugin CLI-backed. Expose clear operations rather than a tool for every CLI command or a generic command runner. Consolidate close variants with similar inputs; keep reading, writing, deleting, and granting access distinct when their arguments or consequences differ. Prefix every public tool name with `fulcra_`.

## Breaking tool renames

- `get_auth_url` → `fulcra_auth`
- `submit_device_code` → `fulcra_auth_device`
- `get_data_catalog` → `fulcra_data_catalog`

Update saved prompts and callers to use the new names. Old public tool aliases are not registered. Internal Python handler names are unchanged. Installed tools take effect in a new Hermes session; changing the development checkout does not update the installed plugin.

## Expansion scope (not implemented yet)

- Catalog filters.
- Data types: create, schema, archive, restore.
- Records: record, get-records, delete.
- Sharing: create, update, delete, leave, list-incoming, list-outgoing, shared-data-types.
- Updates: data-updates.
- Files: upload, download, list, stat, delete, restore, share.

## Reference

Use https://github.com/fulcradynamics/fulcra-context-mcp, especially `fulcra_mcp/tools.py`, as a reference for descriptions and interface design, not as an API backend replacement.

Useful existing patterns include share listing with an incoming/outgoing/both direction, descriptions explaining how tools fit together, timezone-aware date ranges, actionable errors, bounded responses, and explicit sharing scope. Adapt references to the actual Hermes tool names and supported CLI behavior; do not copy MCP-specific limitations or claim unsupported options.
