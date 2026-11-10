"""Reproduce the minimal upstream extraction: python scripts/vendor.py CHECKOUT."""
import ast
from pathlib import Path
import sys

REVISION = '4a4769152e9770406fe66113e49e555f70db9201'
METHODS = {
    'FulcraDataAccessMixin': {'metric_samples'},
    'FulcraAPI': set('''__init__ refresh_access_token refresh_credentials _exchange_refresh_token refresh_if_expiring fulcra_api fulcra_v1alpha1_api_path
        fulcra_v1_records _v0_data_path _decode_jwt_claims get_token_claims get_fulcra_userid
        v1_catalog v1_catalog_data_type v1_catalog_schema resolve_data_type create_datashare
        update_datashare get_datashares delete_datashare data_updates
        get_shared_datasets delete_dataset_permission list_shared_data_types get_user_info
        create_tags create_tag tags create_annotation delete_annotation restore_annotation
        create_data_type update_data_type record_data_type validate_records list_files resolve_filepath upload_file
        download_file delete_file restore_file group_participant'''.split()),
    'FulcraGroupParticipant': set('''__init__ fulcra_api _v0_data_path _v1_group_params
        fulcra_v1alpha1_api_path'''.split()),
}

class Extract(ast.NodeTransformer):
    def __init__(self, module):
        self.module = module

    def visit_ClassDef(self, node):
        if node.name in METHODS:
            node.body = [n for n in node.body if isinstance(n, (ast.Assign, ast.AnnAssign)) or isinstance(n, ast.FunctionDef) and n.name in METHODS[node.name]]
        if node.name == 'FulcraOIDCProvider':
            node.body = [n for n in node.body if not isinstance(n, ast.FunctionDef) or n.name in {'get_device_code', 'get_token', 'refresh_credentials'}]
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        if self.module == 'oidc' and node.name == 'refresh_credentials':
            # A rotating refresh token is also a mutation: one exchange only.
            node.body = node.body[:2] + ast.parse("return self.get_token('refresh_token', payload)").body
        return self.generic_visit(node)

    def visit_Try(self, node):
        if self.module == 'core' and any('self.refresh_credentials()' in ast.unparse(h) for h in node.handlers):
            # Do not replay a denied API request after refreshing credentials.
            return [self.visit(statement) for statement in node.body]
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if ast.unparse(node.func) == 'urllib.request.urlopen':
            node.func = ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='_open', ctx=ast.Load())
            node.keywords = [k for k in node.keywords if k.arg != 'timeout']
        return node


def extract(source, name):
    tree = ast.parse(source)
    if name == 'core':
        tree.body = [n for n in tree.body if
            isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef))]
        tree.body = [n for n in tree.body if not (isinstance(n, ast.Import) and any(a.name in {'pandas', 'webbrowser'} for a in n.names))]
        tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name != '_import_pandas']
    if name == 'connections':
        keep = {'_uuid', 'build_message'}
        tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name in keep]
        tree.body = [n for n in tree.body if not isinstance(n, ast.ImportFrom) or not (n.module or '').startswith('fulcra_api')]
        constants = {'CHANNEL_FIELDS', 'MAX_BODY'}
        tree.body = [n for n in tree.body if not isinstance(n, ast.Assign)
                     or any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
        tree.body = [n for n in tree.body if not (isinstance(n, ast.Import) and any(a.name == 'datetime' for a in n.names))
                     and not (isinstance(n, ast.ImportFrom) and n.module == 'urllib.error')]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('fulcra_api.'):
            node.module, node.level = node.module.removeprefix('fulcra_api.'), 1
    tree = Extract(name).visit(tree)
    return '# Extracted from fulcra-api-python ' + REVISION + '; see PROVENANCE.md.\n' + ast.unparse(ast.fix_missing_locations(tree)) + '\n'


def main():
    source = Path(sys.argv[1])
    # Caller verifies checkout revision; this script does not execute git or import upstream.
    dest = Path(__file__).resolve().parents[1] / '_vendor'
    dest.mkdir(exist_ok=True)
    (dest / '__init__.py').write_text('"""Minimal Fulcra API extraction; not a public SDK."""\n__version__ = "unknown"\n')
    for name in ('core', 'oidc', 'credentials', 'records', 'connections', 'record_validation', 'user_agent'):
        (dest / (name + '.py')).write_text(extract((source / 'fulcra_api' / (name + '.py')).read_text(), name))
    (dest / 'LICENSE').write_bytes((source / 'LICENSE').read_bytes())


if __name__ == '__main__':
    main()
