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

# Detect available container runtime (docker or podman)
detect_runtime() {
    if command -v docker &> /dev/null; then
        echo "docker"
    elif command -v podman &> /dev/null; then
        echo "podman"
    else
        echo ""
    fi
}

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

# Detect container runtime
RUNTIME=$(detect_runtime)
if [[ -z "$RUNTIME" ]]; then
    echo "Error: Neither docker nor podman is installed."
    echo "Please install docker or podman before running this installer."
    exit 1
fi
echo "Detected container runtime: $RUNTIME"
echo ""

# Step 1: Download dingofs-testsuite-tool from GitHub
echo "[1/4] Downloading dingofs-testsuite-tool from GitHub..."
echo "      URL: $TESTSUITE_TOOL_URL"
echo ""

TEMP_FILE=$(mktemp)
DOWNLOAD_SUCCESS=false

# Try direct download first, then with proxy if it fails
if curl -fsSL "$TESTSUITE_TOOL_URL" -o "$TEMP_FILE" 2>&1; then
    DOWNLOAD_SUCCESS=true
elif curl -fsSL --proxy http://hproxy.it.zetyun.cn:1080 "$TESTSUITE_TOOL_URL" -o "$TEMP_FILE" 2>&1; then
    DOWNLOAD_SUCCESS=true
fi

if [[ "$DOWNLOAD_SUCCESS" != "true" ]]; then
    echo "Error: Failed to download dingofs-testsuite-tool"
    rm -f "$TEMP_FILE"
    exit 1
fi

echo "      Downloaded successfully"

# Determine install location (prefer ~/.local/bin if available, else /usr/local/bin)
if [[ -d "$HOME/.local/bin" ]] || mkdir -p "$HOME/.local/bin" 2>/dev/null; then
    INSTALL_DIR="$HOME/.local/bin"
else
    INSTALL_DIR="/usr/local/bin"
fi

DEST_FILE="$INSTALL_DIR/dingofs-testsuite-tool"

# Move temp file to install location (use sudo if needed)
if cp "$TEMP_FILE" "$DEST_FILE" 2>/dev/null; then
    chmod +x "$DEST_FILE"
    echo "      Installed to $DEST_FILE"
elif sudo cp "$TEMP_FILE" "$DEST_FILE" && sudo chmod +x "$DEST_FILE"; then
    echo "      Installed to $DEST_FILE (sudo)"
else
    echo "Error: Failed to install to $DEST_FILE"
    rm -f "$TEMP_FILE"
    exit 1
fi
rm -f "$TEMP_FILE"

# Create symlink for dtt shortcut
if ln -sf "$DEST_FILE" "$INSTALL_DIR/dtt" 2>/dev/null; then
    echo "      Created symlink: $INSTALL_DIR/dtt"
elif sudo ln -sf "$DEST_FILE" "$INSTALL_DIR/dtt" 2>/dev/null; then
    echo "      Created symlink: $INSTALL_DIR/dtt (sudo)"
fi

# Step 2: Pull container image
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo ""
    echo "[2/4] Pulling container image using $RUNTIME..."
    echo "      Image: $IMAGE_NAME"
    echo ""

    # Try pull without proxy first, then with proxy if it fails
    if $RUNTIME pull "$IMAGE_NAME"; then
        PULL_SUCCESS=true
    else
        echo ""
        echo "      Pull failed, retrying with proxy settings..."
        if http_proxy=http://hproxy.it.zetyun.cn:1080 \
           https_proxy=http://hproxy.it.zetyun.cn:1080 \
           $RUNTIME pull "$IMAGE_NAME"; then
            PULL_SUCCESS=true
        else
            PULL_SUCCESS=false
        fi
    fi

    if [[ "$PULL_SUCCESS" == "true" ]]; then
        echo ""
        echo "      Image pulled successfully."
    else
        echo ""
        echo "Error: Image pull failed."
        exit 1
    fi
else
    echo ""
    echo "[2/4] Skipping image pull (--no-pull specified)"
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

# Add ~/.local/bin to PATH if not already there
if [[ -f "$SHELL_PROFILE" ]]; then
    # Add ~/.local/bin to PATH
    if ! grep -q "$HOME/.local/bin" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# dingofs-Testsuite-tools" >> "$SHELL_PROFILE"
        echo "export PATH=\"\$PATH:$HOME/.local/bin\"" >> "$SHELL_PROFILE"
        echo "      Added $HOME/.local/bin to PATH in $SHELL_PROFILE"
    else
        echo "      $HOME/.local/bin already in PATH"
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
echo "[4/4] Setting container image in dingofs-testsuite-tool config..."

dingofs-testsuite-tool config set image "$IMAGE_NAME"

echo ""
echo "=============================================="
echo "Installation complete!"
echo "=============================================="
echo ""
echo "Usage:"
echo "  dtt config show                查看配置"
echo "  dtt config set testdir <path> 设置测试目录 (必填)"
echo "  dtt config set output <path>  设置输出目录 (必填)"
echo ""
echo "Examples:"
echo "  dtt config show                          查看当前配置"
echo "  dtt -t mdtest -s mdtest -n 1             运行 mdtest 快速测试"
echo "  dtt -t fio -s seq_write                  运行 fio 顺序写测试"
echo "  dtt -t ltp -s ltp                        运行 LTP 测试"
echo "  dtt debug                                进入容器调试"
echo "  dtt help                                 查看完整使用手册"
echo ""
echo "Note: 请重新打开终端或运行 'source ~/.bashrc' 使配置生效"
echo ""
