#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHAOS_TOOL_SRC="${DINGOFS_CHAOS_TOOL_SRC:-$PROJECT_ROOT/dingofs-chaos-tool}"
CHAOS_TOOL_DEST="${DINGOFS_CHAOS_TOOL_DEST:-$PROJECT_ROOT/dingofs-chaos-tool}"

if [[ ! -d "$CHAOS_TOOL_SRC/.git" ]]; then
    echo "Error: chaos-tool source is not a Git repository: $CHAOS_TOOL_SRC" >&2
    exit 1
fi

if [[ -n "$(git -C "$CHAOS_TOOL_SRC" status --porcelain --untracked-files=normal)" ]]; then
    echo "Error: chaos-tool source has uncommitted changes: $CHAOS_TOOL_SRC" >&2
    exit 1
fi

if [[ -z "$CHAOS_TOOL_DEST" ]] || [[ "$CHAOS_TOOL_DEST" == "/" ]]; then
    echo "Error: unsafe chaos-tool destination: $CHAOS_TOOL_DEST" >&2
    exit 1
fi

source_head="$(git -C "$CHAOS_TOOL_SRC" rev-parse HEAD)"

source_path="$(realpath "$CHAOS_TOOL_SRC")"
destination_path="$(realpath -m "$CHAOS_TOOL_DEST")"
if [[ "$source_path" == "$destination_path" ]]; then
    echo "Using project-local dingofs-chaos-tool at commit $source_head"
    exit 0
fi

mkdir -p "$CHAOS_TOOL_DEST"

rsync -a --delete --delete-excluded \
    --exclude='/.pytest_cache/' \
    --exclude='/logs/' \
    --exclude='/runs/' \
    --exclude='/var/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$CHAOS_TOOL_SRC/" "$CHAOS_TOOL_DEST/"

destination_head="$(git -C "$CHAOS_TOOL_DEST" rev-parse HEAD)"
if [[ "$destination_head" != "$source_head" ]]; then
    echo "Error: chaos-tool destination HEAD does not match source" >&2
    exit 1
fi

if [[ -n "$(git -C "$CHAOS_TOOL_DEST" status --porcelain --untracked-files=normal)" ]]; then
    echo "Error: chaos-tool destination is not clean after synchronization" >&2
    exit 1
fi

echo "Synchronized dingofs-chaos-tool at commit $source_head"
