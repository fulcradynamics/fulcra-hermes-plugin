"""Fulcra Context plugin for Hermes Agent."""

from pathlib import Path
from . import schemas, tools


def register(ctx):
    """Wire fixed CLI handlers to their typed schemas, then bundled resources."""
    renamed_handlers = {
        "fulcra_auth": tools.fulcra_get_auth_url,
        "fulcra_auth_device": tools.fulcra_submit_device_code,
        "fulcra_data_catalog": tools.fulcra_get_data_catalog,
    }
    for name, schema in schemas.TOOL_SCHEMAS.items():
        handler = renamed_handlers[name] if name in renamed_handlers else getattr(tools, name)
        ctx.register_tool(name=name, toolset="context", schema=schema, handler=handler)

    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.exists():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)
