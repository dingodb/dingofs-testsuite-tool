#!/bin/bash
#
# dingofs-Testsuite-tools Docker Image Builder & Pusher
# Usage: ./build.sh [--debug]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="dingofs-testsuite-tools:latest"
HARBOR_IMAGE="harbor.zetyun.cn/dingofs/dingofs-testsuite-tools:latest"

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
echo "[1/5] Cloning dingofs-integration-test..."
cd "$SCRIPT_DIR"

# Handle old directory name migration
if [[ -d "dingofs-automation-framwork" ]] && [[ ! -d "dingofs-integration-test" ]]; then
    echo "      Renaming old directory to dingofs-integration-test..."
    mv dingofs-automation-framwork dingofs-integration-test
fi

if [[ ! -d "dingofs-integration-test" ]]; then
    git clone git@github.com:dingodb/dingofs-automation-framwork.git dingofs-integration-test
else
    echo "      dingofs-integration-test already exists, pulling latest..."
    cd dingofs-integration-test && git pull && cd ..
fi
echo "      Cloned to $SCRIPT_DIR/dingofs-integration-test"

# Step 1b: Copy dingo binary to build context
echo ""
echo "[2/5] Copying dingo binary..."
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

# Step 2: Build Docker image
echo ""
echo "[3/5] Building Docker image..."
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
        --build-arg http_proxy=http://hproxy.it.zetyun.cn:1080 \
        --build-arg https_proxy=http://hproxy.it.zetyun.cn:1080 \
        . 2>/dev/null; then
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

# Step 3: Tag image for Harbor
echo ""
echo "[4/5] Tagging image for Harbor..."
docker tag "$IMAGE_NAME" "$HARBOR_IMAGE"
echo "      Tagged: $HARBOR_IMAGE"

# Step 4: Push to Harbor
echo ""
echo "[5/5] Pushing to Harbor..."

# Try push without proxy first, then with proxy if it fails
if docker push "$HARBOR_IMAGE" 2>/dev/null; then
    PUSH_SUCCESS=true
else
    echo ""
    echo "      Push failed, retrying with proxy settings..."
    if http_proxy=http://hproxy.it.zetyun.cn:1080 \
       https_proxy=http://hproxy.it.zetyun.cn:1080 \
       docker push "$HARBOR_IMAGE" 2>/dev/null; then
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
