"""Deterministic prose and single-module AST analysis."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys

from . import __version__, phrases


def claims(text):
    text = re.sub(r'```[^\n]*\n.*?(?:```|\Z)', '', text, flags=re.S)
    text = text.replace('`', '').lower()
    def consume(vocabulary):
        nonlocal text
        found = []
        for phrase in sorted(vocabulary, key=len, reverse=True):
            while phrase in text:
                index = text.index(phrase)
                found.append(phrase)
                text = text[:index] + ' ' * len(phrase) + text[index + len(phrase):]
        return found
    negative = consume(phrases.NOBACKGROUNDREMOVAL)
    return consume(phrases.BACKGROUNDREMOVAL), negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    shadow = {n.name for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = (
                    alias.name if alias.asname else alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module or '') + '.' + alias.name
    def resolve(node):
        if isinstance(node, ast.Name):
            if node.id in shadow:
                return ''
            return imports.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''
    def named(node, names):
        value = resolve(node)
        return bool(value) and value.split('.')[-1] in names and value.split('.')[-1] not in shadow
    instances = {}
    def instance(node):
        if isinstance(node, ast.Name):
            return instances.get(node.id)
        if isinstance(node, ast.Call):
            if named(node.func, phrases.REMOVER_CLASSES):
                return 'remover'
            if named(node.func, phrases.WITHOUTBG_CLASSES):
                return 'without'
            if isinstance(node.func, ast.Attribute) and node.func.attr in ('open_weights', 'api'):
                if named(node.func.value, phrases.WITHOUTBG_CLASSES):
                    return 'without'
        return None
    # Resolve assigned instances to a fixed point, allowing simple instance aliases.
    for _ in range(len(list(ast.walk(tree)))):
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                kind = instance(node.value)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and kind and instances.get(target.id) != kind:
                        instances[target.id] = kind
                        changed = True
        if not changed:
            break
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        value = resolve(func)
        root = func
        while isinstance(root, ast.Attribute):
            root = root.value
        imported_root = isinstance(root, ast.Name) and root.id in imports
        if imported_root and value in [s + '.remove' for s in phrases.REMOVE_SOURCES]:
            return True
        if isinstance(func, ast.Attribute):
            if named(func, phrases.GRABCUT_NAMES + phrases.GENERIC_NAMES):
                return True
            if func.attr == 'process' and instance(func.value) == 'remover':
                excluded = any(k.arg == 'type' and isinstance(k.value, ast.Constant)
                               and k.value.value in ('blur', 'map', 'overlay') for k in node.keywords)
                if not excluded:
                    return True
            if func.attr == 'remove_background' and instance(func.value) == 'without':
                return True
        elif isinstance(func, ast.Name) and func.id in imports:
            if named(func, phrases.GRABCUT_NAMES + phrases.GENERIC_NAMES):
                return True
    return False


EXCLUDED = {'.git', '__pycache__', '.venv', 'venv', 'env', '.env', 'virtualenv'}


def audit(repo, ignore=(), verbose=False):
    root = Path(repo)
    if not root.is_dir():
        raise OSError('Repository is not a directory: ' + str(root))
    docs_positive = []
    docs_negative = []
    test_positive = []
    has_evidence = False
    if verbose:
        print('Scope: README.md, docs/**/*.md, tests/ fixtures, Python modules in ' + str(root), file=sys.stderr)
    def walk(directory):
        for path in sorted(directory.iterdir()):
            rel = path.relative_to(root).as_posix()
            if any(rel.startswith(prefix) for prefix in ignore):
                continue
            if path.is_symlink():
                continue
            if path.is_dir():
                if path.name not in EXCLUDED and not (path / 'pyvenv.cfg').exists():
                    yield from walk(path)
            elif path.is_file():
                yield path
    for path in walk(root):
        rel = path.relative_to(root)
        documentation = rel.as_posix() == 'README.md' or (rel.parts[0] == 'docs' and path.suffix == '.md')
        fixture = 'tests' in rel.parts[:-1]
        if path.suffix != '.py' and not documentation and not fixture:
            continue
        text = path.read_text(encoding='utf-8')
        module_evidence = path.suffix == '.py' and evidence(text)
        has_evidence |= module_evidence
        if documentation or fixture:
            positive, negative = claims(text)
            if documentation:
                docs_positive.extend(positive)
                docs_negative.extend(negative)
            elif fixture:
                test_positive.extend(positive)
        if verbose:
            print(str(rel) + ': evidence=' + str(bool(module_evidence)) + ', documentation=' + str(documentation), file=sys.stderr)
    findings = []
    def finding(rule, severity, message):
        findings.append(dict(rule=rule, severity=severity, verdict='FAIL', message=message))
    if docs_positive and not has_evidence:
        finding('documented-image-background-removal-claim-false', 'HIGH', 'Prose claims the checked capability without source evidence.')
    elif test_positive and not docs_positive and not has_evidence:
        finding('documented-image-background-removal-claim-false', 'MEDIUM', 'Only test fixtures claim the checked capability without source evidence.')
    if docs_negative and has_evidence:
        finding('documented-no-image-background-removal-claim-false', 'HIGH', 'Prose denies the checked capability but source evidence is present.')
    return findings


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = commands.add_parser('audit')
    command.add_argument('repo', nargs='?', default='.')
    command.add_argument('--json', action='store_true')
    command.add_argument('--verbose', action='store_true')
    command.add_argument('--ignore', action='append', default=[])
    command.add_argument('--fail-on', choices=['high', 'medium'], default='high')
    try:
        args = parser.parse_args(argv)
        findings = audit(args.repo, args.ignore, args.verbose)
        failed = any(f['severity'] == 'HIGH' or args.fail_on == 'medium' for f in findings)
        verdict = 'FAIL' if failed else 'PASS'
        if args.json:
            print(json.dumps(dict(verdict=verdict, findings=findings)))
        else:
            print(verdict)
            for finding in findings:
                print('{rule} {severity}: {message}'.format(**finding))
        return 2 if failed else 0
    except (OSError, UnicodeError, ValueError) as error:
        print('error: ' + str(error), file=sys.stderr)
        return 1
