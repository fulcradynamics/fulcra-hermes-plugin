"""Fulcra plugin for Hermes Agent: agent messaging and what's new."""
from pathlib import Path

from . import whats_new


def register(ctx):
    """Register hooks, the settings command and skills without starting work.

    Fulcra tools come from the Fulcra MCP server that /fulcra setup adds.
    """
    whats_new.register(ctx)
    for skill in sorted((Path(__file__).parent / 'skills').glob('*/SKILL.md')):
        ctx.register_skill(skill.parent.name, skill)
