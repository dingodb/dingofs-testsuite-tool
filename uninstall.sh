#!/bin/bash
#
# DingoFS Benchmark Tool Uninstaller
# Usage: ./uninstall.sh [--keep-image]
#

set -e

KEEP_IMAGE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-image)
            KEEP_IMAGE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--keep-image]"
            echo "  --keep-image  Keep the Docker image"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.dingofs_benchmark"
IMAGE_NAME="localhost/dingofs-benchmark-tools:latest"

echo "=============================================="
echo "DingoFS Benchmark Tool Uninstaller"
echo "=============================================="
echo ""

# Step 1: Remove symlinks
echo "[1/4] Removing symlinks from /usr/local/bin..."

if [[ -L "/usr/local/bin/dingofs_benchmark_tool" ]]; then
    sudo rm /usr/local/bin/dingofs_benchmark_tool && echo "      Removed /usr/local/bin/dingofs_benchmark_tool"
elif [[ -f "/usr/local/bin/dingofs_benchmark_tool" ]]; then
    echo "      Warning: /usr/local/bin/dingofs_benchmark_tool is not a symlink, skipping"
fi

if [[ -L "/usr/local/bin/dbt" ]]; then
    sudo rm /usr/local/bin/dbt && echo "      Removed /usr/local/bin/dbt"
elif [[ -f "/usr/local/bin/dbt" ]]; then
    echo "      Warning: /usr/local/bin/dbt is not a symlink, skipping"
fi

# Step 2: Remove PATH and alias from shell profile
echo ""
echo "[2/4] Removing from shell profile..."

# Detect shell profile
SHELL_PROFILE=""
if [[ -n "$BASH_VERSION" ]]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        SHELL_PROFILE="$HOME/.bash_profile"
    else
        SHELL_PROFILE="$HOME/.bashrc"
    fi
elif [[ -n "$ZSH_VERSION" ]]; then
    SHELL_PROFILE="$HOME/.zshrc"
fi

if [[ -f "$SHELL_PROFILE" ]]; then
    # Remove PATH export line
    sed -i.bak "\|export PATH=.*dingofs_benchmark_tool|d" "$SHELL_PROFILE" 2>/dev/null || true
    # Remove alias line
    sed -i.bak "/^alias dbt=/d" "$SHELL_PROFILE" 2>/dev/null || true
    # Remove comment line
    sed -i.bak "/# DingoFS Benchmark Tool/d" "$SHELL_PROFILE" 2>/dev/null || true
    rm -f "$SHELL_PROFILE.bak"
    echo "      Cleaned $SHELL_PROFILE"
fi

# Step 3: Remove config directory
echo ""
echo "[3/4] Removing config directory..."

if [[ -d "$CONFIG_DIR" ]]; then
    rm -rf "$CONFIG_DIR" && echo "      Removed $CONFIG_DIR"
else
    echo "      Config directory not found, skipping"
fi

# Step 4: Remove Docker image
echo ""
echo "[4/4] Removing Docker image..."

if [[ "$KEEP_IMAGE" == "false" ]]; then
    # Remove main image
    if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
        docker rmi "$IMAGE_NAME" && echo "      Removed image: $IMAGE_NAME"
    else
        echo "      Image not found, skipping"
    fi

    # Remove dangling (<none>) images
    echo ""
    echo "      Removing dangling images..."
    DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null)
    if [[ -n "$DANGLING" ]]; then
        docker rmi $DANGLING 2>/dev/null && echo "      Removed dangling images" || true
    else
        echo "      No dangling images found"
    fi
else
    echo "      Skipping (--keep-image specified)"
fi

echo ""
echo "=============================================="
echo "Uninstallation complete!"
echo "=============================================="
echo ""
echo "Note: You may need to restart your terminal or run:"
echo "  source ~/.bashrc"
echo ""
