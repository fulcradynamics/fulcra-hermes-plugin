#!/usr/bin/env python3
"""Copy the Agents I Know app from a fulcra-context-mcp checkout into the plugin.

The Desktop page runs the same built app the server offers MCP Apps hosts, shipped with the plugin at a
pinned commit (installed plugins never load code from elsewhere). Copies the current version's bundle to
desktop/agents-i-know.html and records its source in provenance.json; scripts/check-tools.py then checks
the tools it calls.

    scripts/update-app.py <fulcra-context-mcp checkout>
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = 'desktop/agents-i-know.html'

checkout = Path(sys.argv[1]).resolve()
version = re.search(r'^CONTACTS_UI_VERSION = (\d+)$', (checkout / 'fulcra_mcp/apps.py').read_text(), re.M)[1]
source = f'fulcra_mcp/ui/contacts/v{version}.html'
html = (checkout / source).read_bytes()
commit = subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'], text=True).strip()
(ROOT / TARGET).write_bytes(html)

provenance = json.loads((ROOT / 'provenance.json').read_text())
provenance['app'] = {
    'description': 'The Agents I Know MCP App, as the Fulcra MCP server offers it (global view)',
    'repository': 'https://github.com/fulcradynamics/fulcra-context-mcp',
    'commit': commit,
    'source': source,
    'file': TARGET,
    'sha256': hashlib.sha256(html).hexdigest(),
}
(ROOT / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print(f'{TARGET}: v{version} from {commit[:12]}')
