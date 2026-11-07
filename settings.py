"""Canonical persisted setting names for native and command setup."""
NAMES = {
    'updates_enabled': 'updates',
    'mesh_messages_enabled': 'mesh-messages',
    'mesh_invites_enabled': 'mesh-invites',
    'update_interval': 'interval',
    'mesh_agent': 'mesh-agent',
    'updates_data_types': 'updates-data-types',
    'updates_include_files': 'updates-include-files',
    'updates_file_prefixes': 'updates-file-prefixes',
    'updates_ignore_prefixes': 'updates-ignore-prefixes',
}


def get(ctx, key, default=None):
    """Read the canonical persisted key."""
    return ctx.get_config(NAMES[key], default)
