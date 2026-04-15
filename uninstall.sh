#!/bin/bash
#
# dingofs-Testsuite-tools Uninstaller
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

CONFIG_DIR="$HOME/.dingofs_testsuite"
IMAGE_NAME="harbor.zetyun.cn/dingofs/dingofs-testsuite-tools:latest"

echo "=============================================="
echo "dingofs-Testsuite-tools Uninstaller"
echo "=============================================="
echo ""

# Step 1: Remove installed files from ~/.local/bin and /usr/local/bin
echo "[1/4] Removing dingofs-testsuite-tool..."

REMOVED_ANY=false

# Remove from ~/.local/bin first (no sudo needed)
if [[ -f "$HOME/.local/bin/dingofs-testsuite-tool" ]]; then
    rm -f "$HOME/.local/bin/dingofs-testsuite-tool" && echo "      Removed $HOME/.local/bin/dingofs-testsuite-tool"
    REMOVED_ANY=true
fi

if [[ -L "$HOME/.local/bin/dtt" ]]; then
    rm -f "$HOME/.local/bin/dtt" && echo "      Removed $HOME/.local/bin/dtt"
fi

# Remove from /usr/local/bin if exists
if [[ -f "/usr/local/bin/dingofs-testsuite-tool" ]]; then
    sudo rm -f /usr/local/bin/dingofs-testsuite-tool && echo "      Removed /usr/local/bin/dingofs-testsuite-tool"
    REMOVED_ANY=true
fi

if [[ -L "/usr/local/bin/dtt" ]]; then
    sudo rm -f /usr/local/bin/dtt && echo "      Removed /usr/local/bin/dtt"
fi

if [[ "$REMOVED_ANY" == "false" ]]; then
    echo "      No installed files found"
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
    # Remove PATH export lines for dingofs-testsuite
    sed -i.bak "\|export PATH=.*.local/bin|d" "$SHELL_PROFILE" 2>/dev/null || true
    sed -i.bak "\|export PATH=.*dingofs-testsuite|d" "$SHELL_PROFILE" 2>/dev/null || true
    # Remove alias line
    sed -i.bak "/^alias dtt=/d" "$SHELL_PROFILE" 2>/dev/null || true
    # Remove comment line
    sed -i.bak "/# dingofs-Testsuite-tools/d" "$SHELL_PROFILE" 2>/dev/null || true
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
