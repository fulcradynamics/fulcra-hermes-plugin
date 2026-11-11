"""Fulcra plugin for Hermes Agent: agent messaging and what's new."""
from pathlib import Path

from . import messages, tools, whats_new


def register(ctx):
    """Register tools, hooks, the settings command and skills without starting work."""
    for name, schema in tools.TOOL_SCHEMAS.items():
        ctx.register_tool(name=name, toolset='fulcra', schema=schema, handler=getattr(tools, name))
    ctx.register_tool(name='fulcra_receive_agent_messages', toolset='fulcra', schema=messages.SCHEMA,
                      handler=lambda args, **kwargs: messages.tool(ctx.state)(args, **kwargs))
    whats_new.register(ctx)
    for skill in sorted((Path(__file__).parent / 'skills').glob('*/SKILL.md')):
        ctx.register_skill(skill.parent.name, skill)
