# Vendored upstream code

- `fulcra_api/`: from https://github.com/fulcradynamics/fulcra-api-python
- `fulcra_mcp/`: from https://github.com/fulcradynamics/fulcra-context-mcp

Both are Apache-2.0; each directory keeps its upstream `LICENSE`. The pinned revisions are `PINS` in `scripts/vendor.py`. To update, check both out at new revisions, update `PINS` and run:

    python scripts/vendor.py /path/to/fulcra-api-python /path/to/fulcra-context-mcp

The script starts from what plugin modules import from `_vendor` and the attributes they call, follows references through both packages, and keeps only reachable functions, classes, methods, constants, imports and package data. Kept code is unchanged except:

- Docstrings are removed and formatting comes from `ast.unparse`.
- Imports between the two packages are relative.
- Requests go through the plugin's opener (`self._open`), which sets deadlines and drops credentials on cross-origin redirects.
- A request denied for authorization is not replayed after a token refresh, and a refresh makes one token exchange.
- Package data is read with `files(__package__)`.
