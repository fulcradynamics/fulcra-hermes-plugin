"""Launch the real-Hermes safety probe offline in disposable homes.

Exit 1 = unmet safety contract, 2 = probe could not complete, 0 = all contracts met.
"""
import os
from pathlib import Path

import subprocess
import tempfile


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, help='Existing Hermes environment Python (not its bootstrap launcher)')
    parser.add_argument('--source', required=True, help='Matching Hermes source directory')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='plat480-', dir=os.environ['TMPDIR']) as directory:
        root = Path(directory)
        home = root / 'home'
        home.mkdir()
        profile = home / '.hermes'
        profile.mkdir()
        receipt = root / 'receipt'
        env = {
            'PATH': os.environ['PATH'], 'HOME': str(home), 'HERMES_HOME': str(profile),
            'TMPDIR': str(root), 'XDG_CONFIG_HOME': str(root / 'config'),
            'XDG_CACHE_HOME': str(root / 'cache'), 'PYTHONDONTWRITEBYTECODE': '1',
            'UV_OFFLINE': '1', 'HF_HUB_OFFLINE': '1', 'PLAT480_RECEIPT': str(receipt),
        }
        probe = Path(__file__).with_name('redaction_hermes_probe.py').resolve()
        bootstrap = 'import sys, runpy; sys.path.insert(0, sys.argv[1]); runpy.run_path(sys.argv[2], run_name="__main__")'
        run = subprocess.run([args.python, '-I', '-B', '-c', bootstrap, args.source, str(probe)],
                             env=env, cwd=root, timeout=180)
        if run.returncode or not receipt.exists():
            print('PROBE ERROR: runtime failed or no completion receipt')
            return 2
        verdict = receipt.read_text()
        print('PLAT-480 safety contract: ' + verdict, flush=True)
        return {'PASS': 0, 'BLOCKED': 1}.get(verdict, 2)


if __name__ == '__main__':
    try:
        code = main()
    except (OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print('PROBE ERROR: ' + str(exc))
        code = 2
    raise SystemExit(code)
