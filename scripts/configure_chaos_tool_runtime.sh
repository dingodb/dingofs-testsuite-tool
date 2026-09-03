#!/bin/bash

set -euo pipefail

CHAOS_ROOT="${1:?usage: configure_chaos_tool_runtime.sh <chaos-tool-root>}"
DATA_ROOT="$CHAOS_ROOT/var"

if [[ ! -d "$CHAOS_ROOT/config/catalog" ]]; then
    echo "Error: invalid chaos-tool root: $CHAOS_ROOT" >&2
    exit 1
fi

mkdir -p \
    "$DATA_ROOT/history" \
    "$DATA_ROOT/runs" \
    "$DATA_ROOT/logs" \
    "$DATA_ROOT/reports" \
    "$DATA_ROOT/catalog"

for name in runs logs reports; do
    path="$CHAOS_ROOT/$name"
    target="$DATA_ROOT/$name"
    if [[ -L "$path" ]]; then
        if [[ "$(readlink "$path")" != "var/$name" ]]; then
            echo "Error: unexpected chaos-tool runtime link: $path" >&2
            exit 1
        fi
        continue
    fi
    if [[ -d "$path" ]]; then
        cp -a "$path"/. "$target"/
        rm -rf "$path"
    elif [[ -e "$path" ]]; then
        echo "Error: chaos-tool runtime path is not a directory: $path" >&2
        exit 1
    fi
    ln -s "var/$name" "$path"
done

custom_catalog="$CHAOS_ROOT/config/catalog/custom.yaml"
data_catalog="$DATA_ROOT/catalog/custom.yaml"
if [[ -L "$custom_catalog" ]]; then
    if [[ "$(readlink "$custom_catalog")" != "../../var/catalog/custom.yaml" ]]; then
        echo "Error: unexpected chaos-tool custom catalog link: $custom_catalog" >&2
        exit 1
    fi
else
    if [[ -f "$custom_catalog" ]] && [[ ! -e "$data_catalog" ]]; then
        cp -a "$custom_catalog" "$data_catalog"
    elif [[ ! -e "$data_catalog" ]]; then
        printf '{}\n' > "$data_catalog"
    fi
    rm -f "$custom_catalog"
    ln -s "../../var/catalog/custom.yaml" "$custom_catalog"
fi
