#!/bin/bash
#
# dingofs-Testsuite-tools Installer
# Usage: ./install.sh [-n|--no-pull]
#
# This script downloads dingofs-testsuite-tool from GitHub and installs it.
#

set -e

RAW_BASE_URL="https://raw.githubusercontent.com/dingodb/dingofs-testsuite-tool/refs/heads/main"
TESTSUITE_TOOL_URL="$RAW_BASE_URL/dingofs-testsuite-tool"
AI_ANALYZER_URL="$RAW_BASE_URL/dtt-ai-analyze"
AI_SCHEMA_URL="$RAW_BASE_URL/analysis.schema.json"
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

# Step 1: Download the host CLI companions before installing any of them.
echo "[1/4] Downloading DTT host commands from GitHub..."
echo ""

INSTALL_TEMP_DIR=$(mktemp -d)
trap 'rm -rf -- "$INSTALL_TEMP_DIR"' EXIT

download_component() {
    local url="$1"
    local destination="$2"
    local label="$3"
    echo "      $label: $url"
    if curl -fsSL "$url" -o "$destination" 2>&1; then
        return 0
    fi
    if curl -fsSL --proxy http://hproxy.it.zetyun.cn:1080 "$url" -o "$destination" 2>&1; then
        return 0
    fi
    echo "Error: Failed to download $label"
    return 1
}

TEMP_WRAPPER="$INSTALL_TEMP_DIR/dingofs-testsuite-tool"
TEMP_ANALYZER="$INSTALL_TEMP_DIR/dtt-ai-analyze"
TEMP_SCHEMA="$INSTALL_TEMP_DIR/analysis.schema.json"
download_component "$TESTSUITE_TOOL_URL" "$TEMP_WRAPPER" "dingofs-testsuite-tool" || exit 1
download_component "$AI_ANALYZER_URL" "$TEMP_ANALYZER" "dtt-ai-analyze" || exit 1
download_component "$AI_SCHEMA_URL" "$TEMP_SCHEMA" "analysis.schema.json" || exit 1

echo "      Downloaded successfully"

# Determine install location (prefer ~/.local/bin if available, else /usr/local/bin)
if [[ -d "$HOME/.local/bin" ]] || mkdir -p "$HOME/.local/bin" 2>/dev/null; then
    INSTALL_DIR="$HOME/.local/bin"
else
    INSTALL_DIR="/usr/local/bin"
fi

DEST_FILE="$INSTALL_DIR/dingofs-testsuite-tool"
ANALYZER_DEST="$INSTALL_DIR/dtt-ai-analyze"
LIB_DIR="$(dirname "$INSTALL_DIR")/lib/dingofs-testsuite-tool"
SCHEMA_DEST="$LIB_DIR/analysis.schema.json"

install_component() {
    local source="$1"
    local destination="$2"
    local mode="$3"
    local destination_dir staging
    destination_dir=$(dirname "$destination")
    staging="${destination}.tmp.$$"

    if mkdir -p "$destination_dir" 2>/dev/null && \
       install -m "$mode" "$source" "$staging" 2>/dev/null && \
       mv -f "$staging" "$destination" 2>/dev/null; then
        echo "      Installed to $destination"
        return 0
    fi
    rm -f "$staging" 2>/dev/null || true
    if sudo mkdir -p "$destination_dir" && \
       sudo install -m "$mode" "$source" "$staging" && \
       sudo mv -f "$staging" "$destination"; then
        echo "      Installed to $destination (sudo)"
        return 0
    fi
    echo "Error: Failed to install to $destination"
    return 1
}

install_component "$TEMP_WRAPPER" "$DEST_FILE" 0755 || exit 1
install_component "$TEMP_ANALYZER" "$ANALYZER_DEST" 0755 || exit 1
install_component "$TEMP_SCHEMA" "$SCHEMA_DEST" 0644 || exit 1

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

    # Try: direct → direct+sudo → proxy → proxy+sudo
    PULL_CMD="$RUNTIME pull \"$IMAGE_NAME\""
    PULL_SUCCESS=false

    for attempt in \
        "$PULL_CMD" \
        "sudo $PULL_CMD" \
        "http_proxy=http://hproxy.it.zetyun.cn:1080 https_proxy=http://hproxy.it.zetyun.cn:1080 $PULL_CMD" \
        "sudo http_proxy=http://hproxy.it.zetyun.cn:1080 https_proxy=http://hproxy.it.zetyun.cn:1080 $PULL_CMD"; do
        if eval "$attempt"; then
            PULL_SUCCESS=true
            break
        fi
        echo ""
        echo "      Retrying..."
    done

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
