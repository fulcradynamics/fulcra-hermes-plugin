"""Public setting names and read compatibility for pre-PLAT-483 profiles."""
NAMES = {
    'workspace_context_enabled': 'workspace',
    'updates_enabled': 'updates',
    'mesh_messages_enabled': 'mesh-messages',
    'mesh_invites_enabled': 'mesh-invites',
    'workspace_name': 'workspace-name',
    'workspace_role': 'workspace-role',
    'update_interval': 'interval',
    'mesh_agent': 'mesh-agent',
    'updates_data_types': 'updates-data-types',
    'updates_include_files': 'updates-include-files',
    'updates_file_prefixes': 'updates-file-prefixes',
    'updates_ignore_prefixes': 'updates-ignore-prefixes',
}


def get(ctx, key, default=None):
    """Explicit new values, including false/empty, override legacy values."""
    missing = object()
    value = ctx.get_config(NAMES[key], missing)
    return ctx.get_config(key, default) if value is missing else value


def legacy(ctx):
    """Only saved old choices without a new-key override need copying."""
    missing = object()
    return {key: value for key, name in NAMES.items()
            if ctx.get_config(name, missing) is missing
            and (value := ctx.get_config(key, missing)) is not missing}
