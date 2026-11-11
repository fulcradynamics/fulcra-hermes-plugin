"""Extract only the upstream code the plugin uses.

    python scripts/vendor.py FULCRA_API_PYTHON_CHECKOUT FULCRA_CONTEXT_MCP_CHECKOUT

Check out the pinned revisions first; this script does not run git. Starting
from what plugin modules import from `_vendor` and the attributes they read, it
follows references through both packages and keeps only reachable functions,
classes, methods, constants and imports.
"""
import ast
from pathlib import Path
import sys

PINS = {'fulcra_api': '4a4769152e9770406fe66113e49e555f70db9201',
        'fulcra_mcp': '74f5041fbb012991e291697954c38e83901c7a04'}
ROOT = Path(__file__).resolve().parents[1]


class Module:
    def __init__(self, name, source):
        self.name, self.package = name, name.split('.')[0]
        self.tree = ast.parse(source)
        self.defs, self.aliases = {}, {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
            for target in getattr(node, 'targets', []) + [getattr(node, 'target', None)]:
                if isinstance(target, ast.Name):
                    self.defs[target.id] = node
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = self.resolve(node, alias.name)

    def resolve(self, node, name):
        """(module, name) for a vendored import, (module, None) for a module, else None."""
        base = node.module or ''
        if node.level:
            base = self.package + ('.' + base if base else '')
        if base.split('.')[0] not in PINS:
            return None
        return (base, name) if '.' in base else (base + '.' + name, None)

    def methods(self, node, attrs):
        return [n for n in node.body if not isinstance(n, ast.FunctionDef) or n.name in attrs | {'__init__'}]


def references(nodes):
    """Names (with one attribute level) and attributes read by these nodes."""
    names, attrs, imports = set(), set(), []
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            elif isinstance(child, ast.Attribute):
                attrs.add(child.attr)
                if isinstance(child.value, ast.Name):
                    names.add(child.value.id + '.' + child.attr)
            elif isinstance(child, ast.ImportFrom):
                imports.append(child)
    return names, attrs, imports


def reachable(modules, seeds, attrs):
    """Fixpoint: kept definitions, the attributes they read and each module's used names."""
    kept, used = set(seeds), {name: set() for name in modules}
    while True:
        before = (len(kept), len(attrs))
        for module, name in list(kept):
            mod = modules[module]
            node = mod.defs.get(name)
            if node is None:
                continue
            nodes = mod.methods(node, attrs) + node.bases + node.decorator_list if isinstance(node, ast.ClassDef) else [node]
            names, found, imports = references(nodes)
            attrs |= found
            for imp in imports:
                for alias in imp.names:
                    target = mod.resolve(imp, alias.name)
                    if target and target[1]:
                        kept.add(target)
            for ref in names:
                head, _, tail = ref.partition('.')
                used[module].add(head)
                if head in mod.defs:
                    kept.add((module, head))
                target = mod.aliases.get(head)
                if target and target[1]:
                    kept.add(target)
                elif target and tail:
                    kept.add((target[0], tail))
        if (len(kept), len(attrs)) == before:
            return kept, attrs, used


class Transform(ast.NodeTransformer):
    """Plugin request handling and imports; otherwise upstream code is unchanged."""

    def __init__(self, mod, attrs):
        self.mod, self.attrs, self.resources = mod, attrs, []

    def visit_ClassDef(self, node):
        node.body = self.mod.methods(node, self.attrs)
        self.undocument(node)
        return self.generic_visit(node)

    @staticmethod
    def undocument(node):
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) and len(node.body) > 1:
            node.body.pop(0)

    def visit_FunctionDef(self, node):
        self.undocument(node)
        if self.mod.name == 'fulcra_api.oidc' and node.name == 'refresh_credentials':
            # A rotating refresh token is also a mutation: one exchange only.
            node.body = node.body[:2] + ast.parse("return self.get_token('refresh_token', payload)").body
        return self.generic_visit(node)

    def visit_Try(self, node):
        if self.mod.name == 'fulcra_api.core' and any('self.refresh_credentials()' in ast.unparse(h) for h in node.handlers):
            # Do not replay a denied API request after refreshing credentials.
            return [self.visit(statement) for statement in node.body]
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if ast.unparse(node.func) == 'urllib.request.urlopen':
            # The plugin's opener sets deadlines and drops credentials on cross-origin redirects.
            node.func = ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='_open', ctx=ast.Load())
            node.keywords = [k for k in node.keywords if k.arg != 'timeout']
        if ast.unparse(node.func) == f"files('{self.mod.package}').joinpath":
            # Package data travels with the module.
            node.func.value.args = [ast.Name(id='__package__', ctx=ast.Load())]
            self.resources.append(node.args[0].value)
        return node

    def visit_ImportFrom(self, node):
        package = (node.module or '').split('.')[0]
        if not node.level and package in PINS:
            same = package == self.mod.package
            node.module = node.module.partition('.')[2] or None if same else node.module
            node.level = 1 if same else 2
        return node


def render(mod, kept, attrs, used):
    body = []
    for node in mod.tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            node.names = [a for a in node.names if (a.asname or a.name).split('.')[0] in used]
            if node.names:
                body.append(node)
        elif any(mod.defs.get(name) is node for name in kept):
            body.append(node)
    mod.tree.body = body
    transform = Transform(mod, attrs)
    tree = ast.fix_missing_locations(transform.visit(mod.tree))
    header = f'# Extracted from {mod.package} {PINS[mod.package]}; see PROVENANCE.md.\n'
    return header + ast.unparse(tree) + '\n', transform.resources


def plugin_uses():
    """Names plugin modules import from _vendor, and every attribute they read."""
    seeds, attrs = set(), set()
    for path in ROOT.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('_vendor.'):
                seeds |= {(node.module.removeprefix('_vendor.'), a.name) for a in node.names}
            elif isinstance(node, ast.Attribute):
                attrs.add(node.attr)
    return seeds, attrs


def extract(checkouts):
    """{path under _vendor: bytes} for everything the plugin uses from these checkouts."""
    modules = {f'{package}.{path.stem}': Module(f'{package}.{path.stem}', path.read_text())
               for package, checkout in checkouts.items()
               for path in sorted((checkout / package).glob('*.py')) if path.stem != '__init__'}
    kept, attrs, used = reachable(modules, *plugin_uses())
    files = {}
    for package, checkout in checkouts.items():
        files[f'{package}/__init__.py'] = b'__version__ = "unknown"\n' if package == 'fulcra_api' else b''
        files[f'{package}/LICENSE'] = (checkout / 'LICENSE').read_bytes()
    for name, mod in modules.items():
        names = {n for m, n in kept if m == name and n in mod.defs}
        if names:
            package, stem = name.split('.')
            text, resources = render(mod, names, attrs, used[name])
            files[f'{package}/{stem}.py'] = text.encode()
            for resource in resources:
                files[f'{package}/{resource}'] = (checkouts[package] / package / resource).read_bytes()
    return files


def main():
    files = extract(dict(zip(PINS, map(Path, sys.argv[1:3]))))
    for package in PINS:
        for old in (ROOT / '_vendor' / package).rglob('*'):
            if old.is_file():
                old.unlink()
    for path, data in files.items():
        target = ROOT / '_vendor' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


if __name__ == '__main__':
    main()
