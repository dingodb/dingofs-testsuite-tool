#!/bin/bash
#
# dingofs-Testsuite-tools Installer
# Usage: ./install.sh [-n|--no-pull]
#
# This script downloads dingofs-testsuite-tool from GitHub and installs it.
#

set -e

TESTSUITE_TOOL_URL="https://raw.githubusercontent.com/dingodb/dingofs-testsuite-tool/refs/heads/main/dingofs-testsuite-tool"
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

# Step 1: Download dingofs-testsuite-tool from GitHub
echo "[1/4] Downloading dingofs-testsuite-tool from GitHub..."
echo "      URL: $TESTSUITE_TOOL_URL"
echo ""

INSTALL_DIR="/usr/local/bin"
DOWNLOAD_SUCCESS=false

# Try download with proxy first
if curl -fsSL --proxy http://hproxy.it.zetyun.cn:1080 "$TESTSUITE_TOOL_URL" -o "$INSTALL_DIR/dingofs-testsuite-tool" 2>/dev/null; then
    DOWNLOAD_SUCCESS=true
elif curl -fsSL "$TESTSUITE_TOOL_URL" -o "$INSTALL_DIR/dingofs-testsuite-tool" 2>/dev/null; then
    DOWNLOAD_SUCCESS=true
fi

if [[ "$DOWNLOAD_SUCCESS" == "true" ]]; then
    chmod +x "$INSTALL_DIR/dingofs-testsuite-tool"
    echo "      Downloaded to $INSTALL_DIR/dingofs-testsuite-tool"
else
    echo "Error: Failed to download dingofs-testsuite-tool"
    exit 1
fi

# Create symlink for dtt shortcut
if ln -sf "$INSTALL_DIR/dingofs-testsuite-tool" "$INSTALL_DIR/dtt" 2>/dev/null; then
    echo "      Created symlink: /usr/local/bin/dtt"
else
    sudo ln -sf "$INSTALL_DIR/dingofs-testsuite-tool" "$INSTALL_DIR/dtt" 2>/dev/null && \
        echo "      Created symlink: /usr/local/bin/dtt (sudo)"
fi

# Step 2: Pull Docker image
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo ""
    echo "[2/4] Pulling Docker image..."
    echo "      Image: $IMAGE_NAME"
    echo ""

    # Try pull without proxy first, then with proxy if it fails
    if docker pull "$IMAGE_NAME" 2>/dev/null; then
        PULL_SUCCESS=true
    else
        echo ""
        echo "      Pull failed, retrying with proxy settings..."
        if http_proxy=http://hproxy.it.zetyun.cn:1080 \
           https_proxy=http://hproxy.it.zetyun.cn:1080 \
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
    echo ""
    echo "[2/4] Skipping Docker image pull (--no-pull specified)"
fi

# Step 3: Add to PATH via shell profile
echo ""
echo "[3/4] Configuring PATH..."

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

# Add /usr/local/bin to PATH if not already there
if [[ -f "$SHELL_PROFILE" ]]; then
    if ! grep -q "/usr/local/bin" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# dingofs-Testsuite-tools" >> "$SHELL_PROFILE"
        echo "export PATH=\"\$PATH:/usr/local/bin\"" >> "$SHELL_PROFILE"
        echo "      Added /usr/local/bin to PATH in $SHELL_PROFILE"
    else
        echo "      /usr/local/bin already in PATH"
    fi

    # Add alias for dtt if not already there
    if ! grep -q "^alias dtt=" "$SHELL_PROFILE" 2>/dev/null; then
        echo "alias dtt='dingofs-testsuite-tool'" >> "$SHELL_PROFILE"
        echo "      Added 'dtt' alias to $SHELL_PROFILE"
    fi
else
    echo "Warning: Could not detect shell profile, manual setup may be required."
fi

# Step 4: Set image in dingofs-testsuite-tool config
echo ""
echo "[4/4] Setting Docker image in dingofs-testsuite-tool config..."

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
echo "Or use directly:"
echo "  dingofs-testsuite-tool config set testdir /mnt/test"
echo "  dtt -t fio -s seq_write"
echo ""
