"""Fulcra plugin for Hermes Agent: agent contacts, messaging and what's new.

Fulcra's tools come from the hosted Fulcra MCP server, which /fulcra connect adds to Hermes and Hermes signs
in to. The plugin adds skills, the /fulcra command, what's new hooks and a Hermes Desktop page.
"""
import json
from pathlib import Path

from . import commands, mcp_api, whats_new


def register(ctx):
    """Register hooks, the command and skills without network access, writes or background work."""
    mcp_api._FULCRA_CTX = ctx  # dashboard/plugin_api.py calls Fulcra through this ctx.
    whats_new.register(ctx)
    commands.register(ctx)
    for skill in sorted((Path(__file__).parent / 'skills').glob('*/SKILL.md')):
        frontmatter = _frontmatter(skill)
        ctx.register_skill(skill.parent.name, skill, str(frontmatter.get('description') or ''), frontmatter)


def _frontmatter(skill_md):
    """SKILL.md's frontmatter, so the skills index shows each skill's description (Hermes stores
    only what register_skill is given). An unreadable or malformed file registers without one."""
    try:
        text = skill_md.read_text(encoding='utf-8')
    except OSError:
        return {}
    try:
        from agent.skill_utils import parse_frontmatter  # Hermes's own parser, inside Hermes
    except ImportError:
        return _simple_frontmatter(text)
    try:
        frontmatter, _body = parse_frontmatter(text)
        return dict(frontmatter) if isinstance(frontmatter, dict) else {}
    except Exception:
        return {}


def _simple_frontmatter(text):
    """Top-level one-line `key: value` pairs (plain or JSON-quoted) of a `---` block, for outside
    Hermes, where this plugin's skills keep to that form."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return {}
    frontmatter = {}
    for line in lines[1:]:
        if line.strip() == '---':
            return frontmatter
        key, sep, value = line.partition(':')
        if sep and key and not key[0].isspace():
            value = value.strip()
            try:
                value = json.loads(value) if value.startswith('"') else value
            except ValueError:
                pass
            frontmatter[key.strip()] = value
    return {}  # no closing ---
