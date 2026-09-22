# Fulcra Hermes Plugin

This is a [Portable Agent Plugins v1.0.0](https://agent-plugins.org/) wrapper for the [Fulcra Context MCP Server](https://github.com/fulcradynamics/fulcra-context-mcp).

It allows [Hermes Agent](https://github.com/NousResearch/hermes-agent) to seamlessly connect to your Fulcra data by automatically launching the MCP server via `uvx`.

## Installation

You can install this plugin directly into your Hermes Agent environment:

```bash
hermes plugins install fulcradynamics/fulcra-hermes-plugin --no-enable
hermes plugins enable fulcra-context
```

## Requirements

- **uv**: This plugin uses `uvx` to launch the MCP server. You must have [uv](https://github.com/astral-sh/uv) installed on your system.
- **Authentication**: Set your Fulcra API credentials in your Hermes environment (e.g., `FULCRA_API_KEY`). The MCP server will automatically pick these up when Hermes launches it.

## How it works

This repository contains:
1. `plugin.json`: Metadata identifying this as a portable Hermes plugin.
2. `mcp.json`: Configuration telling Hermes to launch `uvx fulcra-context-mcp@latest`.
3. `skills/fulcra-context/SKILL.md`: Guidance prompts teaching Hermes how to correctly utilize the Fulcra Context tools.

Since the core logic lives in the `fulcra-context-mcp` package, this plugin remains lightweight and automatically benefits from upstream improvements to the MCP server.
