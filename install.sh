#!/bin/bash
#
# DingoFS Benchmark Tool Installer
# Usage: ./install.sh [-n|--no-build]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_TOOL="$SCRIPT_DIR/dingofs_benchmark_tool"
IMAGE_NAME="${IMAGE_NAME:-localhost/dingofs-benchmark-tools:latest}"
SKIP_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--no-build)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-n|--no-build]"
            echo "  -n, --no-build  Skip Docker image build"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "DingoFS Benchmark Tool Installer"
echo "=============================================="
echo ""

# Step 1: Build Docker image
if [[ "$SKIP_BUILD" == "false" ]]; then
    echo "[1/3] Building Docker image..."
    echo "      Image: $IMAGE_NAME"
    echo ""

    cd "$SCRIPT_DIR"

    # Try build without proxy first, then with proxy if it fails
    if docker build -t "$IMAGE_NAME" . 2>/dev/null; then
        BUILD_SUCCESS=true
    else
        echo ""
        echo "      Build failed, retrying with proxy settings..."
        if docker build -t "$IMAGE_NAME" \
            --build-arg http_proxy=http://10.220.69.222:1088 \
            --build-arg https_proxy=http://10.220.69.222:1088 \
            . 2>/dev/null; then
            BUILD_SUCCESS=true
        else
            BUILD_SUCCESS=false
        fi
    fi

    if [[ "$BUILD_SUCCESS" == "true" ]]; then
        echo ""
        echo "      Docker image built successfully."
    else
        echo ""
        echo "Error: Docker build failed."
        exit 1
    fi
else
    echo "[1/3] Skipping Docker build (--no-build specified)"
fi

# Step 2: Add dingofs_benchmark_tool to PATH
echo ""
echo "[2/3] Adding dingofs_benchmark_tool to PATH..."

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
    if ! grep -q "dingofs_benchmark_tool" "$SHELL_PROFILE" 2>/dev/null; then
        echo "" >> "$SHELL_PROFILE"
        echo "# DingoFS Benchmark Tool" >> "$SHELL_PROFILE"
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
    if ln -sf "$BENCHMARK_TOOL" /usr/local/bin/dingofs_benchmark_tool 2>/dev/null; then
        echo "      Symlinked to /usr/local/bin/dingofs_benchmark_tool"
    else
        sudo ln -sf "$BENCHMARK_TOOL" /usr/local/bin/dingofs_benchmark_tool 2>/dev/null && \
            echo "      Symlinked to /usr/local/bin/dingofs_benchmark_tool (sudo)"
    fi

    if ln -sf "$BENCHMARK_TOOL" /usr/local/bin/dbt 2>/dev/null; then
        echo "      Symlinked to /usr/local/bin/dbt (shortcut)"
    else
        sudo ln -sf "$BENCHMARK_TOOL" /usr/local/bin/dbt 2>/dev/null && \
            echo "      Symlinked to /usr/local/bin/dbt (shortcut, sudo)"
    fi
fi

# Add alias for dbt in shell profile if not already there
if [[ -f "$SHELL_PROFILE" ]]; then
    if ! grep -q "^alias dbt=" "$SHELL_PROFILE" 2>/dev/null; then
        echo "alias dbt='dingofs_benchmark_tool'" >> "$SHELL_PROFILE"
        echo "      Added 'dbt' alias to $SHELL_PROFILE"
    fi
fi

# Step 3: Set image in dingofs_benchmark_tool config
echo ""
echo "[3/3] Setting Docker image in dingofs_benchmark_tool config..."

# Source the script to use its functions
source "$BENCHMARK_TOOL"

# Set the image
dingofs_benchmark_tool config set image "$IMAGE_NAME"

echo ""
echo "=============================================="
echo "Installation complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Source your shell profile or start a new terminal"
echo "  2. Set test directory: dingofs_benchmark_tool config set testdir /mnt/test"
echo "  3. Set output directory: dingofs_benchmark_tool config set output /tmp/results"
echo "  4. Run a test: dingofs_benchmark_tool -t fio -s seq_write"
echo ""
echo "Or use directly from current terminal:"
echo "  source $BENCHMARK_TOOL"
echo ""
