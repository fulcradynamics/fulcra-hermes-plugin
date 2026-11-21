"""Fulcra plugin for Hermes Agent: agent contacts, messaging and what's new.

Fulcra's tools come from the hosted Fulcra MCP server, which /fulcra connect adds to Hermes and Hermes signs
in to. The plugin adds skills, the /fulcra command, what's new hooks and a Hermes Desktop page.
"""
from pathlib import Path

from . import commands, mcp_api, whats_new


def register(ctx):
    """Register hooks, the command and skills without network access, writes or background work."""
    mcp_api._FULCRA_CTX = ctx  # dashboard/plugin_api.py calls Fulcra tools through this ctx.
    whats_new.register(ctx)
    commands.register(ctx)
    for skill in sorted((Path(__file__).parent / 'skills').glob('*/SKILL.md')):
        ctx.register_skill(skill.parent.name, skill)
