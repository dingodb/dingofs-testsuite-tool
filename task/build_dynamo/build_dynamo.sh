#!/bin/bash
#
# Dynamo 完整编译脚本
# 用法: ./build_dynamo.sh <编译目录> [--skip-deps] [--skip-rust]
# 需先将 dynamo 源码仓库放在脚本同目录下
# 示例: ./build_dynamo.sh /mnt/disk5/build_test/dynamo
#      ./build_dynamo.sh /mnt/disk5/dingo_autotest/client/dynamo --skip-deps
#

set -e

# ===================== 工具函数 =====================
fmt_duration() {
    local s="$1"
    printf "%02d:%02d:%02d" $((s/3600)) $(((s%3600)/60)) $((s%60))
}

STAGES="copy deps rust venv build install verify"
for _stage in ${STAGES}; do
    eval "STAGE_${_stage}=0"
done

# ===================== 参数检查 =====================
SKIP_DEPS=false
SKIP_RUST=false
BUILD_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-deps) SKIP_DEPS=true; shift ;;
        --skip-rust) SKIP_RUST=true; shift ;;
        *)
            if [ -z "${BUILD_DIR}" ]; then
                BUILD_DIR="$1"
            else
                echo "未知参数: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "${BUILD_DIR}" ]; then
    echo "用法: $0 <编译目录> [--skip-deps] [--skip-rust]"
    echo ""
    echo "参数:"
    echo "  编译目录    目标工作目录 (必需)"
    echo "  --skip-deps 跳过系统依赖安装 (已安装过时使用)"
    echo "  --skip-rust 跳过 Rust 安装 (已安装过时使用)"
    echo ""
    echo "注意: 需先将 dynamo 源码仓库放在脚本同目录下"
    echo ""
    echo "示例:"
    echo "  $0 /mnt/disk5/build_test/dynamo"
    echo "  $0 /mnt/disk5/dingo_autotest/client/dynamo --skip-deps --skip-rust"
    exit 1
fi

SCRIPT_DIR="$(realpath "$(dirname "$0")")"
BUILD_DIR="$(realpath -m "${BUILD_DIR}")"
SRC_DIR="${BUILD_DIR}/dynamo"
CORES=$(nproc)

echo "=============================================="
echo "  Dynamo 完整编译"
echo "=============================================="
echo "编译目录   : ${BUILD_DIR}"
echo "源码目录   : ${SRC_DIR}"
echo "CPU 核心数 : ${CORES}"
echo "跳过依赖   : ${SKIP_DEPS}"
echo "跳过 Rust  : ${SKIP_RUST}"
echo "脚本目录   : ${SCRIPT_DIR}"
echo "=============================================="

mkdir -p "${BUILD_DIR}"
SCRIPT_START=$(date +%s)

# ===================== 1. 拷贝源码 =====================
T0=$(date +%s)
echo "[1/8] 拷贝 Dynamo 源码..."

if [ ! -d "${SCRIPT_DIR}/dynamo/.git" ]; then
    echo "错误: 源码仓库不存在: ${SCRIPT_DIR}/dynamo"
    echo "请先在脚本目录下准备好 dynamo 源码:"
    echo "  git clone git@github.com:ai-dynamo/dynamo.git ${SCRIPT_DIR}/dynamo"
    exit 1
fi

if [ "${SRC_DIR}" = "${SCRIPT_DIR}/dynamo" ]; then
    echo "编译目录与源码位置相同，跳过拷贝"
elif [ -d "${SRC_DIR}/.git" ]; then
    echo "源码仓库已存在于编译目录，跳过拷贝: ${SRC_DIR}"
else
    if [ -d "${SRC_DIR}" ]; then
        rm -rf "${SRC_DIR}"
    fi
    cp -a "${SCRIPT_DIR}/dynamo" "${SRC_DIR}"
    echo "已拷贝: dynamo/ -> ${SRC_DIR}"
fi

STAGE_copy=$(($(date +%s) - T0))

# ===================== 2. 安装系统依赖 =====================
T0=$(date +%s)
echo "[2/8] 安装系统依赖..."

if [ "${SKIP_DEPS}" = true ]; then
    echo "跳过系统依赖安装 (--skip-deps)"
elif command -v apt-get &>/dev/null; then
    echo "检测到 apt-get (Ubuntu/Debian)，安装系统依赖..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq build-essential protobuf-compiler libhwloc-dev \
        libsystemd-dev pkg-config clang python3-dev cmake 2>/dev/null || true
    echo "系统依赖安装完成"
elif command -v dnf &>/dev/null; then
    echo "检测到 dnf (RHEL/CentOS)，安装系统依赖..."
    sudo dnf groupinstall -y "Development Tools" 2>/dev/null || true
    sudo dnf --enablerepo=devel install -y protobuf-compiler 2>/dev/null || true
    sudo dnf install -y hwloc-devel systemd-devel pkgconfig clang-devel protobuf-compiler python3-devel cmake
    echo "系统依赖安装完成"
else
    echo "警告: 未检测到包管理器，跳过依赖安装"
fi

STAGE_deps=$(($(date +%s) - T0))

# ===================== 3. 安装 Rust =====================
T0=$(date +%s)
echo "[3/8] 安装 Rust..."

if [ "${SKIP_RUST}" = true ]; then
    echo "跳过 Rust 安装 (--skip-rust)"
elif command -v rustc &>/dev/null; then
    echo "Rust 已安装: $(rustc --version)"
else
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi

# 确保 cargo 在当前 shell 可用
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
    echo "Rust 就绪: $(rustc --version)"
fi

STAGE_rust=$(($(date +%s) - T0))

# ===================== 4. 创建 Python 虚拟环境 =====================
T0=$(date +%s)
echo "[4/8] 创建 Python 虚拟环境..."

cd "${SRC_DIR}"

# 安装 uv
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 确保 uv 可用
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if [ -d ".dynamo" ]; then
    echo "虚拟环境 .dynamo 已存在，跳过创建"
else
    uv venv .dynamo
fi

source .dynamo/bin/activate

# 安装 Python 构建工具
uv pip install pip 'maturin[patchelf]'

STAGE_venv=$(($(date +%s) - T0))

# ===================== 5. 构建 Rust 绑定 =====================
T0=$(date +%s)
echo "[5/8] 构建 Rust 绑定..."

cd "${SRC_DIR}/lib/bindings/python"
export RUSTC_MMAP_OK=0
maturin develop --uv

STAGE_build=$(($(date +%s) - T0))

# ===================== 6. 安装 GPU 内存服务 =====================
T0=$(date +%s)
echo "[6/8] 安装 GPU 内存服务..."

cd "${SRC_DIR}"
uv pip install -e lib/gpu_memory_service

# ===================== 7. 安装 Dynamo Wheel =====================
echo "[7/8] 安装 Dynamo Wheel..."
uv pip install -e .

STAGE_install=$(($(date +%s) - T0))

# ===================== 8. 验证编译 =====================
T0=$(date +%s)
echo "[8/8] 验证编译..."

if python3 -m dynamo.frontend --help &>/dev/null; then
    VERIFY_STATUS="通过"
else
    VERIFY_STATUS="失败"
fi

STAGE_verify=$(($(date +%s) - T0))
TOTAL_ELAPSED=$(($(date +%s) - SCRIPT_START))

# ===================== 输出结果 =====================
echo ""
echo "=============================================="
echo "  编译完成!"
echo "=============================================="
echo "源码目录   : ${SRC_DIR}"
echo "虚拟环境   : ${SRC_DIR}/.dynamo"
echo "验证状态   : ${VERIFY_STATUS}"
echo ""
echo "--- 各阶段耗时 ---"
printf "  %-12s  %s\n" "拷贝源码"   "$(fmt_duration ${STAGE_copy})"
printf "  %-12s  %s\n" "系统依赖"   "$(fmt_duration ${STAGE_deps})"
printf "  %-12s  %s\n" "Rust安装"   "$(fmt_duration ${STAGE_rust})"
printf "  %-12s  %s\n" "Python环境" "$(fmt_duration ${STAGE_venv})"
printf "  %-12s  %s\n" "Rust绑定"   "$(fmt_duration ${STAGE_build})"
printf "  %-12s  %s\n" "安装Wheel"  "$(fmt_duration ${STAGE_install})"
printf "  %-12s  %s\n" "验证"       "$(fmt_duration ${STAGE_verify})"
printf "  %-12s  %s\n" "总耗时"     "$(fmt_duration ${TOTAL_ELAPSED})"
echo "=============================================="

if [ "${VERIFY_STATUS}" = "通过" ]; then
    echo "编译成功！Dynamo 已就绪。"
    echo "激活环境: cd ${SRC_DIR} && source .dynamo/bin/activate"
    exit 0
else
    echo "警告: 验证未通过，请检查编译日志"
    exit 1
fi
