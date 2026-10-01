"""Reproduce the minimal upstream extraction: python scripts/vendor.py CHECKOUT."""
import ast
from pathlib import Path
import sys

REVISION = '66949bac42920c841facd567a02d6d6c4e01e824'
METHODS = {
    'FulcraDataAccessMixin': {'metric_samples'},
    'FulcraAPI': set('''__init__ refresh_access_token fulcra_api fulcra_v1alpha1_api_path
        fulcra_v1_records _v0_data_path _decode_jwt_claims get_token_claims get_fulcra_userid
        v1_catalog v1_catalog_data_type v1_catalog_schema resolve_data_type create_datashare
        update_datashare get_datashares delete_datashare data_updates
        get_shared_datasets delete_dataset_permission list_shared_data_types get_user_info
        create_tags create_tag tags create_annotation delete_annotation restore_annotation
        record_data_type validate_records list_files resolve_filepath upload_file
        download_file delete_file restore_file group_participant'''.split()),
    'FulcraGroupParticipant': set('''__init__ fulcra_api _v0_data_path _v1_group_params
        fulcra_v1alpha1_api_path'''.split()),
}

class Extract(ast.NodeTransformer):
    def visit_ClassDef(self, node):
        if node.name in METHODS:
            node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in METHODS[node.name]]
        if node.name == 'FulcraOIDCProvider':
            node.body = [n for n in node.body if not isinstance(n, ast.FunctionDef) or n.name in {'get_device_code', 'get_token', 'refresh_credentials'}]
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if ast.unparse(node.func) == 'urllib.request.urlopen':
            node.func = ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr='_open', ctx=ast.Load())
        return node


def extract(source, name):
    tree = ast.parse(source)
    if name == 'core':
        tree.body = [n for n in tree.body if
            isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef))]
        tree.body = [n for n in tree.body if not (isinstance(n, ast.Import) and any(a.name in {'pandas', 'webbrowser'} for a in n.names))]
    if name == 'records':
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == 'fulcra_api.core':
                node.module, node.level = 'core', 1
    tree = Extract().visit(tree)
    return '# Extracted from fulcra-api-python ' + REVISION + '; see PROVENANCE.md.\n' + ast.unparse(ast.fix_missing_locations(tree)) + '\n'


def main():
    source = Path(sys.argv[1])
    # Caller verifies checkout revision; this script does not execute git or import upstream.
    dest = Path(__file__).resolve().parents[1] / '_vendor'
    dest.mkdir(exist_ok=True)
    (dest / '__init__.py').write_text('"""Minimal Fulcra API extraction; not a public SDK."""\n')
    for name in ('core', 'oidc', 'credentials', 'records'):
        (dest / (name + '.py')).write_text(extract((source / 'fulcra_api' / (name + '.py')).read_text(), name))
    (dest / 'LICENSE').write_bytes((source / 'LICENSE').read_bytes())


if __name__ == '__main__':
    main()
