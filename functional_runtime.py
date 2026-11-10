#!/usr/bin/env python3
"""Immutable guided runtime boundary. Standard library only; host Python >=3.9.

Capability reads inspect local image metadata only. Framework imports and remote
connections belong to the container, after a second complete integrity check.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys

FEATURES = ['exact_case_plan_v1', 'runtime_context_v1', 'owned_cleanup_v1',
            'lifecycle_events_v2', 'cancel_boundary_v1', 'inspection_v1']
REQUIRED = ['run_tests.py', 'requirements.txt', 'pytest.ini',
            'src/test_runner/functional_plan.py', 'src/test_runner/runtime_context.py',
            'src/test_runner/resource_journal.py', 'src/test_runner/owned_resources.py',
            'src/test_runner/functional_events.py', 'src/test_runner/functional_redaction.py',
            'src/test_runner/functional_contracts.py', 'src/test_runner/functional_capabilities.py',
            'src/config/ssh_client.py', 'src/config/env_parser.py']
SOURCE_DIRS = ('src', 'conf', 'testcases', 'scripts', 'tools', 'template')
SOURCE_ROOTS = ('run_tests.py', 'requirements.txt', 'pytest.ini', 'pyproject.toml',
                'setup.cfg', 'setup.py', 'conftest.py', 'functional_protocol.json')
HEX = re.compile(r'[a-f0-9]{64}')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4194304), b''):
            value.update(chunk)
    return value.hexdigest()


def safe_file(root, name, aliases=None):
    relative = PurePosixPath(name)
    if not name or relative.is_absolute() or '..' in relative.parts or str(relative) != name:
        raise ValueError('Invalid runtime relative path')
    path = root / name
    if any(part.is_symlink() for part in path.parents) or not path.is_file():
        raise ValueError('Missing or symlinked runtime file: ' + name)
    if aliases and name in aliases:
        target=safe_file(root,aliases[name])
        if not path.is_symlink() or path.resolve()!=target:
            raise ValueError('Functional runtime alias target mismatch: '+name)
    elif path.is_symlink():
        raise ValueError('Undeclared runtime symlink: '+name)
    return path


def collect_source(root, aliases=None):
    """Preserve all runtime trees, including base configuration and case includes."""
    paths = []
    for name in SOURCE_ROOTS:
        path = root / name
        if path.exists() or path.is_symlink():
            paths.append(path)
    for name in SOURCE_DIRS:
        directory = root / name
        if directory.is_symlink():
            raise ValueError('Runtime source directory cannot be a symlink')
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_symlink():
                    safe_file(root,path.relative_to(root).as_posix(),aliases)
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    paths.append(path)
    result = {path.relative_to(root).as_posix(): digest(safe_file(root, path.relative_to(root).as_posix(),aliases))
              for path in sorted(paths)}
    if not set(REQUIRED) <= result.keys():
        raise ValueError('Incomplete functional framework protocol files')
    declaration = json.loads(safe_file(root, 'functional_protocol.json').read_text())
    if (declaration.get('version') != 2 or declaration.get('context_version') != 1
            or declaration.get('event_version') != 2
            or set(declaration.get('features', [])) != set(FEATURES)):
        raise ValueError('Unsupported functional framework protocol')
    if not any(name.startswith('conf/') for name in result) or not any(name.startswith('testcases/') for name in result):
        raise ValueError('Incomplete functional configuration or cases')
    return result


def capability(root, inspect_image=True):
    document = json.loads(safe_file(root, 'functional-runtime.json').read_text())
    cap = document['functional_runtime']
    if (set(cap) != {'version', 'features', 'files', 'image_id', 'source_manifest'}
            or cap['version'] != 2 or set(cap['features']) != set(FEATURES)
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', cap['image_id'])):
        raise ValueError('Invalid functional runtime capabilities')
    if document['architecture'] != platform.machine():
        raise ValueError('Functional runtime CPU architecture mismatch')
    files = cap['files']
    if not isinstance(files, dict) or not {'dingofs-testsuite-tool', 'entrypoint.sh', 'functional_runtime.py'} <= files.keys():
        raise ValueError('Incomplete functional runtime files')
    aliases={}
    if 'functional-aliases.json' in files:
        alias_path=safe_file(root,'functional-aliases.json')
        if digest(alias_path)!=files['functional-aliases.json']:
            raise ValueError('Functional alias manifest digest mismatch')
        aliases=json.loads(alias_path.read_text())
        if not isinstance(aliases,dict) or any(not isinstance(target,str) or target in aliases for target in aliases.values()):
            raise ValueError('Invalid functional source aliases')
    package_aliases={'dingofs-integration-test/'+name:'dingofs-integration-test/'+target for name,target in aliases.items()}
    for name, expected in files.items():
        if not isinstance(expected, str) or not HEX.fullmatch(expected) or digest(safe_file(root, name,package_aliases)) != expected:
            raise ValueError('Functional runtime file digest mismatch: ' + name)
    if not package_aliases.keys() <= files.keys():
        raise ValueError('Unlisted functional source alias')
    source = collect_source(root / 'dingofs-integration-test',aliases)
    if source != cap['source_manifest'] or any(files.get('dingofs-integration-test/' + name) != sha for name, sha in source.items()):
        raise ValueError('Functional runtime source manifest mismatch')
    if inspect_image:
        runtime = runtime_engine(root)
        result = subprocess.run([runtime, 'image', 'inspect', cap['image_id']],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        image = json.loads(result.stdout)[0]
        arch = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(image['Architecture'])
        if image['Id'] != cap['image_id'] or image['Os'] != 'linux' or arch != document['architecture']:
            raise ValueError('Functional runtime image identity or architecture mismatch')
    return cap


def runtime_engine(root):
    config = root / 'config/runtime'
    value = config.read_text().strip() if config.is_file() else 'docker'
    if value not in ('docker', 'podman'):
        raise ValueError('Functional runtime requires docker or podman')
    return value


def read_context(path, cap):
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Functional context requires an absolute regular file')
    context = json.loads(path.read_text())
    required = {'version', 'parent_id', 'child_id', 'module', 'env_name', 'retries', 'source_manifest',
                'approved_targets', 'resolved_targets', 'functional_runtime'}
    if set(context) != required or context['version'] != 1:
        raise ValueError('Invalid functional context fields')
    if type(context['retries']) is not int or not 0 <= context['retries'] <= 5:
        raise ValueError('Invalid frozen retry budget')
    for key in ('parent_id', 'child_id', 'module', 'env_name'):
        if not isinstance(context[key], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', context[key]):
            raise ValueError('Invalid functional context identity')
    if context['functional_runtime'] != cap:
        raise ValueError('Functional runtime changed since approval')
    source = context['source_manifest']
    if not isinstance(source, dict) or not source or any(cap['source_manifest'].get(name) != sha for name, sha in source.items()):
        raise ValueError('Approved source manifest differs from installed runtime')
    if not isinstance(context['approved_targets'], list) or not context['approved_targets']:
        raise ValueError('Missing approved targets')
    approved=set()
    for target in context['approved_targets']:
        if (not isinstance(target,dict) or set(target)!={'host','user','role','mutates'}
                or not isinstance(target['mutates'],bool)
                or any(not isinstance(target[key],str) or not target[key] for key in ('host','user','role'))):
            raise ValueError('Invalid approved target fields')
        approved.add((target['host'],target['user']))
    targets = context['resolved_targets']
    if not isinstance(targets, list) or not targets:
        raise ValueError('Missing resolved target routes')
    routes={}
    for route in targets:
        if not isinstance(route,dict) or set(route) != {'source_host', 'machine_id', 'machine_name', 'address', 'port', 'user'}:
            raise ValueError('Invalid resolved target route')
        ipaddress.ip_address(route['address'])
        if type(route['port']) is not int or not 1 <= route['port'] <= 65535:
            raise ValueError('Invalid resolved SSH port')
        for host in (route['source_host'],route['address']):
            identity=(host,route['user'])
            if identity not in approved:
                raise ValueError('Resolved SSH route is not approved')
            endpoint=(route['address'],route['port'],route['user'])
            if identity in routes and routes[identity]!=endpoint:
                raise ValueError('Conflicting resolved SSH routes')
            routes[identity]=endpoint
    if not approved <= routes.keys():
        raise ValueError('Approved target is missing its resolved SSH route')
    return context


def launch(root, argv):
    parser = argparse.ArgumentParser(description='Launch one approved functional child')
    parser.add_argument('-t', '--tool', choices=['int'], required=True)
    parser.add_argument('-s', '--scenario', required=True)
    parser.add_argument('--env', required=True)
    parser.add_argument('--case-plan', type=Path, required=True)
    parser.add_argument('--functional-context', type=Path, required=True)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args(argv)
    # Validate all local bytes and approval before inspecting/starting a container.
    cap = capability(root, inspect_image=False)
    context = read_context(args.functional_context, cap)
    if args.scenario != context['module'] or args.env != context['env_name']:
        raise ValueError('CLI module or environment differs from approved context')
    if not args.case_plan.is_absolute() or args.case_plan.is_symlink() or not args.case_plan.is_file():
        raise ValueError('Case plan requires an absolute regular file')
    plan = json.loads(args.case_plan.read_text())
    if plan.get('version') != 1 or set(plan.get('modules', {})) != {context['module']}:
        raise ValueError('Case plan must select exactly the approved child module')
    capability(root)
    output = args.output.absolute() / context['parent_id'] / context['child_id']
    if output.exists() and (output.is_symlink() or any(output.iterdir())):
        raise ValueError('Functional child output must be an unused directory')
    if any(path.is_symlink() for path in output.parents):
        raise ValueError('Functional output cannot traverse a symlink')
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    output.chmod(0o700)
    command = [runtime_engine(root), 'run', '--rm', '--pull=never', '--net=host',
               '--entrypoint', '/entrypoint.sh',
               '-v', str(root) + ':/functional-runtime:ro',
               '-v', str(root / 'dingofs-integration-test') + ':/dingofs-integration-test:ro',
               '-v', str(root / 'entrypoint.sh') + ':/entrypoint.sh:ro',
               '-v', str(args.case_plan) + ':' + str(args.case_plan) + ':ro',
               '-v', str(args.functional_context) + ':' + str(args.functional_context) + ':ro',
               '-v', str(output) + ':/output',
               '--tmpfs', '/root/.ssh:rw,noexec,nosuid,mode=0700',
               '--tmpfs', '/functional-home:rw,noexec,nosuid,mode=0700',
               '-e', 'HOME=/functional-home', '-e', 'SSH_AUTH_SOCK=',
               '-e', 'DTT_FUNCTIONAL_OUTPUT_DIR=/output',
               '-e', 'DTT_INT_RERUNS=' + str(context['retries']),
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'INT_ENV=' + args.env,
               '-e', 'INT_CASE_PLAN=' + str(args.case_plan),
               '-e', 'INT_FUNCTIONAL_CONTEXT=' + str(args.functional_context),
               cap['image_id'], '-t', 'int', '-s', args.scenario, '-o', '/output']
    return subprocess.call(command)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent
    if argv == ['--functional-capabilities', '--format', 'json']:
        print(json.dumps(capability(root), sort_keys=True))
        return 0
    if argv[:1] == ['--verify-container']:
        if sys.version_info < (3, 10):
            raise ValueError('Guided container requires Python 3.10 or newer')
        cap = capability(root, inspect_image=False)
        read_context(Path(argv[1]), cap)
        return 0
    return launch(root, argv)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        print('Functional runtime validation failed: ' + str(exc), file=sys.stderr)
        sys.exit(2)
