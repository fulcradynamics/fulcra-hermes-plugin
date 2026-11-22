"""Native boundary contracts; no production requests."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType('native_plugin')
pkg.__path__ = [str(ROOT)]
sys.modules['native_plugin'] = pkg


class NativeTests(unittest.TestCase):
    def test_runtime_has_no_process_or_heavy_imports(self):
        import ast
        banned = {'subprocess', 'uv', 'pandas', 'numpy', 'pyarrow', 'dateparser', 'click'}
        files = [*ROOT.glob('*.py'), *ROOT.joinpath('_vendor').rglob('*.py')]
        for path in files:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({n.name.split('.')[0] for n in node.names} & banned, path)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], banned, path)
                elif isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), {'os.system', 'os.popen', 'eval', 'exec', '__import__'}, path)



if __name__ == '__main__':
    unittest.main()
