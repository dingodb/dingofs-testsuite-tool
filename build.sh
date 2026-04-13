#!/bin/bash
#
# dingofs-Testsuite-tools Docker Image Builder & Pusher
# Usage: ./build.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="dingofs-testsuite-tools:latest"
HARBOR_IMAGE="harbor.zetyun.cn/dingofs/dingofs-testsuite-tools:latest"

echo "=============================================="
echo "dingofs-Testsuite-tools Builder & Pusher"
echo "=============================================="
echo ""

# Step 1: Build Docker image
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

# Step 2: Tag image for Harbor
echo ""
echo "[2/3] Tagging image for Harbor..."
docker tag "$IMAGE_NAME" "$HARBOR_IMAGE"
echo "      Tagged: $HARBOR_IMAGE"

# Step 3: Push to Harbor
echo ""
echo "[3/3] Pushing to Harbor..."

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
