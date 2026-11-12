#!/usr/bin/env python3
"""Prepare a reviewed image-native DTT context and optionally build it locally."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

DEFAULT_BASE = 'harbor.zetyun.cn/dingofs/dingofs-testsuite-tools@sha256:0b88cdc552b5633cc672736ca1a09a61bea0ef0f5c7aed27c0254b38ce83da95'
LAUNCHERS = ('dingofs-testsuite-tool', 'dtt-ai-analyze', 'analysis.schema.json',
             'entrypoint.sh', 'functional_runtime.py')
SCRIPTS = ('performance_benchmark.py', 'performance_plan.py', 'performance_report.py',
           'performance_tools.py', 'ai_storage_scenarios.py')


def ignored(path):
    return any(part in {'.git', '__pycache__', '.pytest_cache'} for part in path.parts) or path.suffix in {'.pyc', '.pyo'}


def prepare(source, context):
    source = source.resolve()
    context = context.absolute()
    if context.exists() and (context.is_symlink() or not context.is_dir() or any(context.iterdir())):
        raise ValueError('Build context must be a new or empty directory')
    if context.resolve().is_relative_to(source):
        raise ValueError('Build context must be outside the source root')
    spec = importlib.util.spec_from_file_location('dtt_build_runtime', source / 'functional_runtime.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    root = source / 'dingofs-integration-test'
    paths = []
    aliases = {}
    for name in runtime.SOURCE_ROOTS + runtime.SOURCE_DIRS:
        path = root / name
        if path.is_symlink():
            raise ValueError('Root source alias is forbidden: ' + name)
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            for child in path.rglob('*'):
                if ignored(child.relative_to(root)):
                    continue
                if child.is_symlink():
                    target = child.resolve()
                    if (name != 'testcases' or not child.is_file()
                            or not target.is_relative_to(path.resolve())
                            or any(parent.is_symlink() for parent in child.parents)
                            or ignored(target.relative_to(root))):
                        raise ValueError('Invalid source alias: ' + str(child))
                    aliases[child.relative_to(root).as_posix()] = target.relative_to(root).as_posix()
                if child.is_file():
                    paths.append(child)
    for name in LAUNCHERS:
        if (source / name).is_symlink() or not (source / name).is_file():
            raise ValueError('Missing regular launcher: ' + name)
    context.mkdir(parents=True, exist_ok=True)
    tree = context / 'dingofs-integration-test'
    for path in paths:
        name = path.relative_to(root).as_posix()
        destination = tree / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name in aliases:
            destination.symlink_to(os.path.relpath(tree / aliases[name], destination.parent))
        else:
            shutil.copy2(path, destination)
    manifest = runtime.collect_source(tree, aliases)
    package = context / 'package'
    package.mkdir()
    for name in LAUNCHERS:
        shutil.copy2(source / name, package / name)
    scripts = context / 'scripts'
    scripts.mkdir()
    for name in SCRIPTS:
        path = source / 'scripts' / name
        if name == 'ai_storage_scenarios.py' and not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing regular script: ' + name)
        shutil.copy2(path, package / name)
        shutil.copy2(path, scripts / name)
    document = {'tool': 'dtt', 'entrypoint': 'dingofs-testsuite-tool',
                'architecture': platform.machine(), 'source_location': 'image',
                'files': {p.name: runtime.digest(p) for p in sorted(package.iterdir())},
                'source_manifest': manifest, 'source_aliases': aliases,
                'functional_features': runtime.FEATURES}
    (package / 'image-manifest.json').write_text(json.dumps(document, sort_keys=True, indent=2) + '\n')
    shutil.copy2(Path(__file__).resolve().parents[1] / 'Dockerfile.platform', context / 'Dockerfile')
    return document



def resolve_base_image(value):
    """Dockerfile FROM requires a repository reference, not a local image ID."""
    if re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}', value):
        return value
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', value):
        raise ValueError('--base-image requires an immutable repository digest or local SHA256 image ID')
    def inspect(reference):
        result = subprocess.run(['docker', 'image', 'inspect', reference], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        return json.loads(result.stdout)[0]
    image = inspect(value)
    if image.get('Id') == value:
        for reference in image.get('RepoDigests') or []:
            if re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}', reference):
                if inspect(reference).get('Id') == value:
                    return reference
    raise ValueError('Local image ID has no verified repository digest; supply --base-image repository@sha256:<digest>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--base-image', default=DEFAULT_BASE)
    parser.add_argument('--tag', default='dtt-platform:local')
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    try:
        base_image = resolve_base_image(args.base_image)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    prepare(args.source_root, args.context)
    if not args.no_build:
        subprocess.run(['docker', 'build', '--pull=false', '--network=none', '--build-arg',
                        'BASE_IMAGE=' + base_image, '--tag', args.tag, str(args.context)], check=True)
    print(json.dumps({'context': str(args.context.absolute()), 'tag': args.tag, 'built': not args.no_build}))


if __name__ == '__main__':
    main()
