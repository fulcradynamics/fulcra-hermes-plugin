#!/usr/bin/env python3
"""Check every tool the plugin's skills call exists on the Fulcra MCP server.

Lists the tools a fulcra-context-mcp checkout offers on /mcp (the endpoint the
user adds to Hermes) and compares them with every `tool_name(` call written in
the skills. Also refuses calls to tools only MCP App panels use, which Hermes
can't display.

    scripts/check-tools.py <fulcra-context-mcp checkout>

Exits 1 on any problem, except tools in OPTIONAL, which the skills only use
when the server offers them.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# Tools a skill calls only if offered, with the alternative it falls back to.
OPTIONAL: dict[str, str] = {
    "accept_agent_invitation": "Connecting with the generic tools",
}
# Tools the skills name only to say Hermes doesn't use them (no MCP App panels).
NOT_CALLED = {"open_agent_contacts", "open_file_manager"}

LIST_TOOLS = """
import asyncio, json
from fastmcp import Client
import fulcra_mcp.main as main
async def go():
    async with Client(main.mcp) as c:
        tools = await c.list_tools()
    ui = lambda t: (t.meta or {}).get("ui") or {}
    print(json.dumps({t.name: ui(t).get("visibility") == ["app"] or bool(ui(t).get("resourceUri")) for t in tools}))
asyncio.run(go())
"""

CALL = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\(")


def offered(checkout: str) -> dict[str, bool]:
    """Tool name -> whether only MCP App panels use it (or it opens one)."""
    out = subprocess.run(
        ["uv", "run", "--directory", checkout, "python", "-c", LIST_TOOLS],
        env={**os.environ, "FULCRA_ENVIRONMENT": "prod"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


def called() -> dict[str, list[str]]:
    calls: dict[str, list[str]] = {}
    for path in sorted(SKILLS.rglob("*.md")):
        for name in CALL.findall(path.read_text()):
            calls.setdefault(name, []).append(str(path.relative_to(ROOT)))
    return calls


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    tools = offered(sys.argv[1])
    missing = 0
    for name, where in sorted(called().items()):
        if name in tools or name in NOT_CALLED:
            continue
        files = ", ".join(sorted(set(where)))
        if name in OPTIONAL:
            print(f"optional, not offered: {name} ({OPTIONAL[name]}) in {files}")
        else:
            print(f"MISSING: {name} in {files}")
            missing += 1
    for name, where in sorted(called().items()):
        if tools.get(name) and name not in NOT_CALLED:
            print(f"PANEL-ONLY: {name} in {', '.join(sorted(set(where)))}")
            missing += 1
    print(f"/mcp: {len(tools)} tools offered; {missing} problems")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
