#!/bin/bash
#
# dingofs-Testsuite-tools Docker Image Builder & Pusher
# Usage: ./build.sh [--debug]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="dingofs-testsuite-tools:latest"
HARBOR_IMAGE="harbor.zetyun.cn/dingofs/dingofs-testsuite-tools:latest"

install_local_cli() {
    local install_dir="${DTT_INSTALL_DIR:-$HOME/.local/bin}"
    local installed_cli="$install_dir/dingofs-testsuite-tool"

    mkdir -p "$install_dir"
    install -m 0755 "$SCRIPT_DIR/dingofs-testsuite-tool" "$installed_cli"
    ln -sfn "$installed_cli" "$install_dir/dtt"
    echo "      Updated local CLI: $installed_cli"
}

# Check for --debug flag
DEBUG_MODE=false
if [[ "$1" == "--debug" ]]; then
    DEBUG_MODE=true
fi

echo "=============================================="
echo "dingofs-Testsuite-tools Builder & Pusher"
echo "=============================================="
echo ""

# Step 1: Clone dingofs-integration-test to build context
echo "[1/6] Cloning dingofs-integration-test..."
cd "$SCRIPT_DIR"

# Handle old directory name migration
if [[ -d "dingofs-automation-framwork" ]] && [[ ! -d "dingofs-integration-test" ]]; then
    echo "      Renaming old directory to dingofs-integration-test..."
    mv dingofs-automation-framwork dingofs-integration-test
fi

if [[ ! -d "dingofs-integration-test" ]]; then
    git clone git@github.com:dingodb/dingofs-integration-test.git dingofs-integration-test
else
    echo "      dingofs-integration-test already exists, pulling latest..."
    cd dingofs-integration-test && git pull && cd ..
fi
echo "      Cloned to $SCRIPT_DIR/dingofs-integration-test"

# Step 2: Synchronize dingofs-chaos-tool to build context
echo ""
echo "[2/6] Updating and synchronizing dingofs-chaos-tool..."
CHAOS_TOOL_DIR="$SCRIPT_DIR/dingofs-chaos-tool"
if [[ ! -d "$CHAOS_TOOL_DIR/.git" ]]; then
    echo "Error: dingofs-chaos-tool is not a Git repository: $CHAOS_TOOL_DIR" >&2
    exit 1
fi
if [[ -n "$(git -C "$CHAOS_TOOL_DIR" status --porcelain --untracked-files=normal)" ]]; then
    echo "Error: dingofs-chaos-tool has uncommitted changes: $CHAOS_TOOL_DIR" >&2
    exit 1
fi
git -C "$CHAOS_TOOL_DIR" pull --ff-only
"$SCRIPT_DIR/scripts/sync_chaos_tool.sh"

# Step 3: Copy dingo binary to build context
echo ""
echo "[3/6] Copying dingo binary..."
DINGO_SRC="/home/jenkins/code/dingofs/scripts/docker/rocky9/dingofs/tools/sbin/dingo"
DINGO_DEST="$SCRIPT_DIR/dingo"
mkdir -p "$(dirname "$DINGO_DEST")"
if [[ -f "$DINGO_SRC" ]]; then
    cp "$DINGO_SRC" "$DINGO_DEST"
    chmod +x "$DINGO_DEST"
    echo "      Copied dingo to $DINGO_DEST"
else
    echo "      Warning: dingo not found at $DINGO_SRC"
fi

# Step 4: Build Docker image
echo ""
echo "[4/6] Building Docker image..."
echo "      Image: $IMAGE_NAME"
echo ""

cd "$SCRIPT_DIR"

# Try build without proxy first, then with proxy if it fails
if docker build -t "$IMAGE_NAME" . ; then
    BUILD_SUCCESS=true
else
    echo ""
    echo "      Build failed, retrying with proxy settings..."
    if docker build -t "$IMAGE_NAME" \
        --build-arg http_proxy=http://hproxy.it.zetyun.cn:1080 \
        --build-arg https_proxy=http://hproxy.it.zetyun.cn:1080 \
        . ; then
        BUILD_SUCCESS=true
    else
        BUILD_SUCCESS=false
    fi
fi

if [[ "$BUILD_SUCCESS" != "true" ]]; then
    echo ""
    echo "Error: Docker build failed."
    exit 1
fi

echo ""
echo "      Docker image built successfully."
install_local_cli

if [[ "$DEBUG_MODE" == "true" ]]; then
    # Skip tagging and push in debug mode
    echo ""
    echo "=============================================="
    echo "Build complete (debug mode - no push)"
    echo "=============================================="
    echo ""
    echo "Image: $IMAGE_NAME"
    echo ""
    echo "Automation framework installed at: /dingofs-integration-test"
    exit 0
fi

# Step 5: Tag image for Harbor
echo ""
echo "[5/6] Tagging image for Harbor..."
docker tag "$IMAGE_NAME" "$HARBOR_IMAGE"
echo "      Tagged: $HARBOR_IMAGE"

# Step 6: Push to Harbor
echo ""
echo "[6/6] Pushing to Harbor..."

# Try push without proxy first, then with proxy if it fails
if docker push "$HARBOR_IMAGE" ; then
    PUSH_SUCCESS=true
else
    echo ""
    echo "      Push failed, retrying with proxy settings..."
    if http_proxy=http://hproxy.it.zetyun.cn:1080 \
       https_proxy=http://hproxy.it.zetyun.cn:1080 \
       docker push "$HARBOR_IMAGE" ; then
        PUSH_SUCCESS=true
    else
        PUSH_SUCCESS=false
    fi
fi

if [[ "$PUSH_SUCCESS" == "true" ]]; then
    echo ""
    echo "      Docker image pushed successfully."
else
    echo ""
    echo "Error: Docker image push failed."
    exit 1
fi

echo ""
echo "=============================================="
echo "Build and push complete!"
echo "=============================================="
echo ""
echo "Image pushed: $HARBOR_IMAGE"
echo ""
echo "Automation framework installed at: /dingofs-integration-test"
