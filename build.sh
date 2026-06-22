#!/usr/bin/env bash
set -euo pipefail

APP_NAME="RecorderAnalyzer"
APP_DISPLAY_NAME="手工测试流量智能分析工具"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
DIST_DIR="${SCRIPT_DIR}/dist"
VENV_DIR="${SCRIPT_DIR}/.venv-build"
BROWSER_DIR="${SCRIPT_DIR}/browser"
DESKTOP_FILE="${SCRIPT_DIR}/packaging/${APP_NAME}.desktop"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[build]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ok]${NC} $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $1"; }
err()   { echo -e "${RED}[err ]${NC} $1"; exit 1; }

# ──────────────────────────────────────
# 1. 检测系统
# ──────────────────────────────────────
detect_os() {
    info "检测操作系统..."
    OS_ID=""
    OS_LIKE=""
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID}"
        OS_LIKE="${ID_LIKE:-}"
    fi
    ARCH="$(uname -m)"
    info "  系统: ${PRETTY_NAME:-unknown} (${ARCH})"
    info "  内核: $(uname -r)"

    case "${OS_ID}" in
        kylin|neokylin)
            info "  检测到麒麟操作系统"
            OS_FAMILY="debian"
            ;;
        ubuntu|debian|deepin|uos)
            info "  检测到 Debian 系操作系统"
            OS_FAMILY="debian"
            ;;
        fedora|centos|rhel|anolis|openEuler)
            info "  检测到 RPM 系操作系统"
            OS_FAMILY="rpm"
            ;;
        *)
            if echo "${OS_LIKE}" | grep -qi "debian"; then
                OS_FAMILY="debian"
            elif echo "${OS_LIKE}" | grep -qi "rhel\|fedora"; then
                OS_FAMILY="rpm"
            else
                warn "未识别的系统: ${OS_ID}，默认使用 Debian 系流程"
                OS_FAMILY="debian"
            fi
            ;;
    esac
}

# ──────────────────────────────────────
# 2. 安装系统依赖
# ──────────────────────────────────────
install_system_deps() {
    info "检查系统依赖..."

    local pkgs=()
    if [ "${OS_FAMILY}" = "debian" ]; then
        pkgs=(
            python3 python3-venv python3-pip python3-dev
            binutils patchelf
            libgtk-3-0 libgtk-3-dev
            libxcb-cursor0 libxcb-xinerama0
            libxkbcommon-x11-0
            libegl1-mesa libgl1-mesa-glx
            libpulse-mainloop-glib0
            libnss3 libnspr4
            xvfb
        )
        if command -v apt-get &>/dev/null; then
            info "  使用 apt-get 安装 ${#pkgs[@]} 个系统依赖..."
            info "  包列表: ${pkgs[*]}"
            sudo apt-get update -qq
            sudo apt-get install -y "${pkgs[@]}"
            ok "系统依赖安装完成"
        else
            warn "未找到 apt-get，请手动安装依赖: ${pkgs[*]}"
        fi
    elif [ "${OS_FAMILY}" = "rpm" ]; then
        pkgs=(
            python3 python3-venv python3-pip python3-devel
            binutils patchelf
            gtk3 gtk3-devel
            libxcb libxcb-devel
            libxkbcommon-x11
            mesa-libEGL mesa-libGL
            nss nspr
            xorg-x11-server-Xvfb
        )
        if command -v dnf &>/dev/null; then
            info "  使用 dnf 安装 ${#pkgs[@]} 个系统依赖..."
            info "  包列表: ${pkgs[*]}"
            sudo dnf install -y "${pkgs[@]}"
            ok "系统依赖安装完成"
        elif command -v yum &>/dev/null; then
            info "  使用 yum 安装 ${#pkgs[@]} 个系统依赖..."
            info "  包列表: ${pkgs[*]}"
            sudo yum install -y "${pkgs[@]}"
            ok "系统依赖安装完成"
        else
            warn "未找到 dnf/yum，请手动安装依赖: ${pkgs[*]}"
        fi
    fi
}

# ──────────────────────────────────────
# 3. 设置 Python 虚拟环境
# ──────────────────────────────────────
setup_venv() {
    info "设置 Python 虚拟环境..."

    if [ ! -d "${VENV_DIR}" ]; then
        python3 -m venv "${VENV_DIR}"
        ok "虚拟环境已创建: ${VENV_DIR}"
    else
        ok "虚拟环境已存在: ${VENV_DIR}"
    fi

    source "${VENV_DIR}/bin/activate"

    info "  升级 pip..."
    pip install --upgrade pip -q

    info "  安装 requirements.txt 依赖..."
    pip install -r "${SCRIPT_DIR}/requirements.txt"
    ok "requirements.txt 依赖安装完成"

    info "  安装 pyinstaller..."
    pip install pyinstaller
    ok "pyinstaller 安装完成"

    # Playwright 浏览器
    info "安装 Playwright Chromium 到 ${BROWSER_DIR} ..."
    info "  这将下载约 400MB 数据，请耐心等待..."
    PLAYWRIGHT_BROWSERS_PATH="${BROWSER_DIR}" python -m playwright install chromium \
        && ok "Playwright Chromium 已下载到 ${BROWSER_DIR}" \
        || warn "Playwright 浏览器下载失败，可在运行时自动下载"
}
# ──────────────────────────────────────
# 4. 清理
# ──────────────────────────────────────
clean_build() {
    info "清理构建产物..."
    rm -rf "${BUILD_DIR}" "${DIST_DIR}" "${SCRIPT_DIR:?}/${APP_NAME}.spec"
    ok "清理完成"
}

# ──────────────────────────────────────
# 5. 构建可执行文件
# ──────────────────────────────────────
do_build() {
    info "构建 ${APP_NAME} (${ARCH})..."

    source "${VENV_DIR}/bin/activate"

    mkdir -p "${DIST_DIR}" "${BUILD_DIR}"

    pyinstaller \
        --onefile \
        --name "${APP_NAME}" \
        --add-data "core:core" \
        --add-data "ui:ui" \
        --add-data "fonts:fonts" \
        --hidden-import core \
        --hidden-import ui \
        --hidden-import core.models \
        --hidden-import core.analyzer \
        --hidden-import core.generator \
        --hidden-import core.executor \
        --hidden-import core.recorder \
        --hidden-import ui.panels \
        --hidden-import ui.app \
        --collect-all flet \
        --collect-all playwright \
        --noconfirm \
        --log-level WARN \
        main.py

    ok "构建完成: ${DIST_DIR}/${APP_NAME}"

    # 复制浏览器到 dist 目录（供离线使用）
    if [ -d "${BROWSER_DIR}" ] && [ -n "$(ls -A "${BROWSER_DIR}" 2>/dev/null)" ]; then
        info "复制浏览器到 ${DIST_DIR}/browser ..."
        cp -a "${BROWSER_DIR}" "${DIST_DIR}/browser"
        local browser_size
        browser_size=$(du -sh "${DIST_DIR}/browser" | cut -f1)
        ok "浏览器已打包: ${browser_size}"
    else
        warn "未找到 browser/ 目录，运行时将自动下载"
    fi

    # 验证
    if [ -f "${DIST_DIR}/${APP_NAME}" ]; then
        local size
        size=$(du -h "${DIST_DIR}/${APP_NAME}" | cut -f1)
        info "  可执行文件大小: ${size}"
        file "${DIST_DIR}/${APP_NAME}"
    fi
}

# ──────────────────────────────────────
# 6. 创建桌面入口
# ──────────────────────────────────────
install_desktop_entry() {
    info "安装桌面入口..."

    mkdir -p "${SCRIPT_DIR}/packaging"

    cat > "${DESKTOP_FILE}" << EOF
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Comment=录制浏览器操作并自动生成 API 测试集合
Exec=${DIST_DIR}/${APP_NAME}
Icon=${SCRIPT_DIR}/packaging/${APP_NAME}.png
Terminal=false
Categories=Development;Utility;
StartupWMClass=${APP_NAME}
EOF

    # 生成 SVG 图标（简易）
    if [ ! -f "${SCRIPT_DIR}/packaging/${APP_NAME}.png" ]; then
        info "  请将应用图标放置于 packaging/${APP_NAME}.png"
    fi

    # 安装到用户目录
    local user_desktop="${HOME}/.local/share/applications/${APP_NAME}.desktop"
    mkdir -p "$(dirname "${user_desktop}")"
    cp "${DESKTOP_FILE}" "${user_desktop}"
    ok "桌面入口已安装: ${user_desktop}"

    # 可选：安装到系统目录
    if [ "${EUID:-0}" -eq 0 ] && [ -d /usr/share/applications ]; then
        cp "${DESKTOP_FILE}" /usr/share/applications/
        ok "桌面入口已安装到系统: /usr/share/applications/${APP_NAME}.desktop"
    fi
}

# ──────────────────────────────────────
# 7. 打包为 .deb
# ──────────────────────────────────────
build_deb() {
    info "打包 .deb ..."

    local deb_root="${BUILD_DIR}/deb/${APP_NAME}"
    local deb_dir="${deb_root}/DEBIAN"
    local deb_bin="${deb_root}/usr/bin"
    local deb_share="${deb_root}/usr/share/${APP_NAME}"
    local deb_desktop="${deb_root}/usr/share/applications"
    local deb_icon="${deb_root}/usr/share/icons/hicolor/256x256/apps"

    mkdir -p "${deb_dir}" "${deb_bin}" "${deb_share}" "${deb_desktop}" "${deb_icon}"

    # control
    cat > "${deb_dir}/control" << EOF
Package: ${APP_NAME}
Version: 1.0.0
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.10), libgtk-3-0, libxcb-cursor0, libxkbcommon-x11-0, libegl1-mesa, libnss3, libnspr4
Maintainer: RecorderAnalyzer
Description: ${APP_DISPLAY_NAME}
 录制浏览器操作、分析 HTTP 请求、生成 Postman 集合。
EOF

    # 复制二进制
    cp "${DIST_DIR}/${APP_NAME}" "${deb_bin}/"

    # 复制浏览器到 /usr/share/RecorderAnalyzer/browser （FHS 标准）
    if [ -d "${DIST_DIR}/browser" ]; then
        cp -a "${DIST_DIR}/browser" "${deb_share}/browser"
    fi

    # 桌面入口
    if [ -f "${DESKTOP_FILE}" ]; then
        cp "${DESKTOP_FILE}" "${deb_desktop}/"
    fi

    # 图标
    if [ -f "${SCRIPT_DIR}/packaging/${APP_NAME}.png" ]; then
        cp "${SCRIPT_DIR}/packaging/${APP_NAME}.png" "${deb_icon}/"
    fi

    # 构建 .deb
    local deb_output="${DIST_DIR}/${APP_NAME}_1.0.0_${ARCH}.deb"
    dpkg-deb --build "${deb_root}" "${deb_output}" 2>/dev/null

    if [ -f "${deb_output}" ]; then
        ok ".deb 包: ${deb_output}"
    else
        warn ".deb 打包失败"
    fi
}

# ──────────────────────────────────────
# 8. 单独下载浏览器
# ──────────────────────────────────────
download_browser() {
    info "下载 Playwright Chromium 到 ${BROWSER_DIR} ..."
    info "  这将下载约 400MB 数据，请耐心等待..."
    mkdir -p "${BROWSER_DIR}"
    PLAYWRIGHT_BROWSERS_PATH="${BROWSER_DIR}" python -m playwright install chromium --with-deps
    local size
    size=$(du -sh "${BROWSER_DIR}" | cut -f1)
    ok "Playwright Chromium 已下载: ${BROWSER_DIR} (${size})"
}

# ──────────────────────────────────────
# 主流程
# ──────────────────────────────────────
main() {
    echo ""
    echo "============================================"
    echo "  ${APP_DISPLAY_NAME}"
    echo "  构建脚本 — Linux (麒麟/统信/UOS/Deepin)"
    echo "============================================"
    echo ""

    detect_os

    case "${1:-all}" in
        deps)
            install_system_deps
            setup_venv
            ;;
        clean)
            clean_build
            exit 0
            ;;
        build)
            [ ! -d "${VENV_DIR}" ] && setup_venv
            do_build
            ;;
        deb)
            [ ! -d "${DIST_DIR}" ] && do_build
            build_deb
            ;;
        desktop)
            install_desktop_entry
            ;;
        browser)
            source "${VENV_DIR}/bin/activate"
            download_browser
            ;;
        all)
            install_system_deps
            setup_venv
            clean_build
            do_build
            install_desktop_entry
            build_deb
            ;;
        *)
            echo "用法: $0 {all|deps|build|deb|desktop|browser|clean}"
            echo "  all      完整构建（默认，含浏览器下载）"
            echo "  deps     安装系统依赖 + Python 依赖"
            echo "  build    仅构建可执行文件"
            echo "  deb      打包为 .deb"
            echo "  desktop  安装桌面快捷方式"
            echo "  browser  单独下载 Playwright Chromium 到 browser/"
            echo "  clean    清理构建产物"
            exit 0
            ;;
    esac

    echo ""
    ok "已完成！"
    echo ""
    echo "  可执行文件: ${DIST_DIR}/${APP_NAME}"
    echo "  .deb 包:     ${DIST_DIR}/${APP_NAME}_1.0.0_${ARCH}.deb (如果启用)"
    echo ""
    echo "  在终端无头环境运行: xvfb-run ${DIST_DIR}/${APP_NAME}"
    echo ""
}

main "$@"
