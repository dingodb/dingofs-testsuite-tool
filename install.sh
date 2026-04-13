#!/bin/bash
#
# dingofs-Testsuite-tools Installer
# Usage: ./install.sh [-n|--no-pull]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTSUITE_TOOL="$SCRIPT_DIR/dingofs-testsuite-tool"
IMAGE_NAME="${IMAGE_NAME:-harbor.zetyun.cn/dingofs/dingofs-testsuite-tools:latest}"
SKIP_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--no-pull)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-n|--no-pull]"
            echo "  -n, --no-pull  Skip Docker image pull"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "dingofs-Testsuite-tools Installer"
echo "=============================================="
echo ""

# Step 1: Pull Docker image
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "[1/3] Pulling Docker image..."
    echo "      Image: $IMAGE_NAME"
    echo ""

    # Try pull without proxy first, then with proxy if it fails
    if docker pull "$IMAGE_NAME" 2>/dev/null; then
        PULL_SUCCESS=true
    else
        echo ""
        echo "      Pull failed, retrying with proxy settings..."
        if http_proxy=http://10.220.69.222:1088 \
           https_proxy=http://10.220.69.222:1088 \
           docker pull "$IMAGE_NAME" 2>/dev/null; then
            PULL_SUCCESS=true
        else
            PULL_SUCCESS=false
        fi
    fi

    if [[ "$PULL_SUCCESS" == "true" ]]; then
        echo ""
        echo "      Docker image pulled successfully."
    else
        echo ""
        echo "Error: Docker image pull failed."
        exit 1
    fi
else
    echo "[1/3] Skipping Docker image pull (--no-pull specified)"
fi

# Step 2: Add dingofs-testsuite-tool to PATH
echo ""
echo "[2/3] Adding dingofs-testsuite-tool to PATH..."

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

# Add to shell profile if not already there
if [[ -f "$SHELL_PROFILE" ]]; then
    if ! grep -q "dingofs-testsuite-tool" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# dingofs-Testsuite-tools" >> "$SHELL_PROFILE"
        echo "export PATH=\"\$PATH:$SCRIPT_DIR\"" >> "$SHELL_PROFILE"
        echo "      Added to $SHELL_PROFILE"
    else
        echo "      Already configured in $SHELL_PROFILE"
    fi
else
    echo "Warning: Could not detect shell profile, manual setup may be required."
fi

# Create symlinks in /usr/local/bin
if [[ -d "/usr/local/bin" ]]; then
    # Try direct write first, then sudo if it fails
    if ln -sf "$TESTSUITE_TOOL" /usr/local/bin/dingofs-testsuite-tool 2>/dev/null; then
        echo "      Symlinked to /usr/local/bin/dingofs-testsuite-tool"
    else
        sudo ln -sf "$TESTSUITE_TOOL" /usr/local/bin/dingofs-testsuite-tool 2>/dev/null && \
            echo "      Symlinked to /usr/local/bin/dingofs-testsuite-tool (sudo)"
    fi

    if ln -sf "$TESTSUITE_TOOL" /usr/local/bin/dtt 2>/dev/null; then
        echo "      Symlinked to /usr/local/bin/dtt (shortcut)"
    else
        sudo ln -sf "$TESTSUITE_TOOL" /usr/local/bin/dtt 2>/dev/null && \
            echo "      Symlinked to /usr/local/bin/dtt (shortcut, sudo)"
    fi
fi

# Add alias for dtt in shell profile if not already there
if [[ -f "$SHELL_PROFILE" ]]; then
    if ! grep -q "^alias dtt=" "$SHELL_PROFILE" 2>/dev/null; then
        echo "alias dtt='dingofs-testsuite-tool'" >> "$SHELL_PROFILE"
        echo "      Added 'dtt' alias to $SHELL_PROFILE"
    fi
fi

# Step 3: Set image in dingofs-testsuite-tool config
echo ""
echo "[3/3] Setting Docker image in dingofs-testsuite-tool config..."

# Source the script to use its functions
source "$TESTSUITE_TOOL"

# Set the image
dingofs-testsuite-tool config set image "$IMAGE_NAME"

echo ""
echo "=============================================="
echo "Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Source your shell profile or start a new terminal"
echo "  2. Set test directory: dingofs-testsuite-tool config set testdir /mnt/test"
echo "  3. Set output directory: dingofs-testsuite-tool config set output /tmp/results"
echo "  4. Run a test: dingofs-testsuite-tool -t fio -s seq_write"
echo ""
echo "Or use directly from current terminal:"
echo "  source $TESTSUITE_TOOL"
echo ""
