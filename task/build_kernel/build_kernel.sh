#!/bin/bash
#
# Linux 内核完整编译脚本
# 用法: ./build_kernel.sh <编译目录> [内核版本]
# 需先将源码包 linux-<版本>.tar.xz 放在脚本同目录下
# 示例: ./build_kernel.sh /mnt/disk5/dingo_autotest/client/linuxkernel
#      ./build_kernel.sh /mnt/disk5/dingo_autotest/client/linuxkernel 6.6.87
#

set -e

# ===================== 工具函数 =====================
fmt_duration() {
    local s="$1"
    printf "%02d:%02d:%02d" $((s/3600)) $(((s%3600)/60)) $((s%60))
}

STAGES="copy extract configure compile verify"
for _stage in ${STAGES}; do
    eval "STAGE_${_stage}=0"
done

# ===================== 参数检查 =====================
if [ $# -lt 1 ]; then
    echo "用法: $0 <编译目录> [内核版本]"
    echo ""
    echo "参数:"
    echo "  编译目录    目标工作目录 (必需)"
    echo "  内核版本    内核版本号，默认 6.6.87 (可选)"
    echo ""
    echo "注意: 需先将 linux-<版本>.tar.xz 放在脚本同目录下"
    echo ""
    echo "示例:"
    echo "  $0 /mnt/disk5/dingo_autotest/client/linuxkernel"
    echo "  $0 /mnt/disk5/dingo_autotest/client/linuxkernel 6.6.87"
    exit 1
fi

SCRIPT_DIR="$(realpath "$(dirname "$0")")"
BUILD_DIR="$(realpath "$1")"
KERNEL_VER="${2:-6.6.87}"
SRC_DIR="${BUILD_DIR}/linux-${KERNEL_VER}"
TARBALL="linux-${KERNEL_VER}.tar.xz"
DISTRO_CONFIG="/boot/config-$(uname -r)"
CORES=$(nproc)

echo "=============================================="
echo "  Linux 内核完整编译"
echo "=============================================="
echo "编译目录   : ${BUILD_DIR}"
echo "内核版本   : ${KERNEL_VER}"
echo "CPU 核心数 : ${CORES}"
echo "发行版配置 : ${DISTRO_CONFIG}"
echo "脚本目录   : ${SCRIPT_DIR}"
echo "=============================================="

mkdir -p "${BUILD_DIR}"
SCRIPT_START=$(date +%s)

# ===================== 1. 拷贝源码包 =====================
T0=$(date +%s)
echo "[1/6] 拷贝源码包..."

if [ ! -f "${SCRIPT_DIR}/${TARBALL}" ]; then
    echo "错误: 源码包不存在: ${SCRIPT_DIR}/${TARBALL}"
    echo "请先将 ${TARBALL} 放在脚本同目录下"
    exit 1
fi

if [ -f "${BUILD_DIR}/${TARBALL}" ]; then
    echo "源码包已存在于编译目录，跳过拷贝: ${BUILD_DIR}/${TARBALL}"
elif [ -d "${SRC_DIR}" ]; then
    echo "源码目录已存在，跳过拷贝和解压"
else
    cp "${SCRIPT_DIR}/${TARBALL}" "${BUILD_DIR}/${TARBALL}"
    echo "已拷贝: ${TARBALL} -> ${BUILD_DIR}/"
fi

STAGE_copy=$(($(date +%s) - T0))

# ===================== 2. 解压源码 =====================
T0=$(date +%s)
echo "[2/6] 解压内核源码到: ${SRC_DIR}"

if [ -d "${SRC_DIR}" ]; then
    echo "源码目录已存在，跳过解压"
else
    tar -xf "${BUILD_DIR}/${TARBALL}" -C "${BUILD_DIR}"
    # 检查脚本目录是否有预解压的源码，有的话直接拷贝（比 tar 解压更快）
    if [ -d "${SCRIPT_DIR}/linux-${KERNEL_VER}" ]; then
        echo "检测到脚本目录已有解压好的源码，使用拷贝（更快）"
        rm -rf "${SRC_DIR}"
        cp -a "${SCRIPT_DIR}/linux-${KERNEL_VER}" "${SRC_DIR}"
    fi
    rm -f "${BUILD_DIR}/${TARBALL}"
fi

cd "${SRC_DIR}"
STAGE_extract=$(($(date +%s) - T0))

# ===================== 3. 配置内核 =====================
T0=$(date +%s)
echo "[3/6] 配置内核..."

if [ -f "${DISTRO_CONFIG}" ]; then
    cp "${DISTRO_CONFIG}" .config
    echo "使用发行版配置: ${DISTRO_CONFIG}"
else
    make defconfig
    echo "发行版配置不可用，使用 defconfig"
fi

# 禁用模块签名（编译环境通常没有签名证书）
scripts/config --disable MODULE_SIG      2>/dev/null || true
scripts/config --set-str MODULE_SIG_KEY ""       2>/dev/null || true
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""  2>/dev/null || true
scripts/config --set-str SYSTEM_REVOCATION_KEYS "" 2>/dev/null || true
scripts/config --disable DEBUG_INFO_BTF          2>/dev/null || true

# 对齐新旧版本的配置差异
make olddefconfig

echo "配置项: $(grep -c '=' .config)"
echo "编译为模块: $(grep -c '=m' .config)"
echo "编译进内核: $(grep -c '=y' .config)"

STAGE_configure=$(($(date +%s) - T0))

# ===================== 4. 编译 =====================
T0=$(date +%s)
echo "[4/6] 开始编译 (make -j${CORES})..."

make -j"${CORES}"

STAGE_compile=$(($(date +%s) - T0))

# ===================== 5. 验证结果 =====================
T0=$(date +%s)
echo "[5/6] 验证编译产物..."

BZIMAGE="${SRC_DIR}/arch/x86/boot/bzImage"
MODULE_COUNT=$(find "${SRC_DIR}" -name "*.ko" 2>/dev/null | wc -l)
BUILD_SIZE=$(du -sh "${SRC_DIR}" 2>/dev/null | cut -f1)

STAGE_verify=$(($(date +%s) - T0))
TOTAL_ELAPSED=$(($(date +%s) - SCRIPT_START))

echo ""
echo "=============================================="
echo "  编译完成!"
echo "=============================================="
echo "内核镜像   : ${BZIMAGE}"
echo "内核版本   : $(cat ${SRC_DIR}/include/config/kernel.release 2>/dev/null)"
echo "编译模块   : ${MODULE_COUNT} 个 .ko"
echo "目录大小   : ${BUILD_SIZE}"
echo ""
echo "--- 各阶段耗时 ---"
printf "  %-12s  %s\n" "拷贝源码包" "$(fmt_duration ${STAGE_copy})"
printf "  %-12s  %s\n" "解压源码"   "$(fmt_duration ${STAGE_extract})"
printf "  %-12s  %s\n" "配置内核"   "$(fmt_duration ${STAGE_configure})"
printf "  %-12s  %s\n" "编译"       "$(fmt_duration ${STAGE_compile})"
printf "  %-12s  %s\n" "验证产物"   "$(fmt_duration ${STAGE_verify})"
printf "  %-12s  %s\n" "总耗时"     "$(fmt_duration ${TOTAL_ELAPSED})"
echo "=============================================="

if [ -f "${BZIMAGE}" ]; then
    file "${BZIMAGE}"
    echo ""
    echo "编译成功！内核镜像已生成。"
    exit 0
else
    echo "错误: 未找到 bzImage，编译可能失败"
    exit 1
fi
