#!/bin/bash
# proxyCodex — macOS 一键启动脚本
# 使用方法: chmod +x start.sh && ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROXY_URL="http://127.0.0.1:3000/v1/models"
PYTHON=""

# 检测 Python
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[FAIL] 未检测到 Python 3.8+，请先安装: https://www.python.org/downloads/"
    exit 1
fi

echo "========================================"
echo "  proxyCodex — macOS 一键启动"
echo "========================================"

# 首次配置
if [ ! -f "$SCRIPT_DIR/providers.json" ] || ! grep -q '"api_key": "[^"]\{4,\}"' "$SCRIPT_DIR/providers.json" 2>/dev/null; then
    echo "[..] 首次使用，进入配置模式..."
    cd "$SCRIPT_DIR" && $PYTHON proxyCodex.py --setup
fi

# 检查代理是否已在运行
if curl -sf "$PROXY_URL" > /dev/null 2>&1; then
    echo "[OK] 代理已在运行"
else
    # 启动代理（后台）
    echo "[..] 启动代理..."
    cd "$SCRIPT_DIR" && nohup $PYTHON proxyCodex.py > /tmp/proxyCodex.log 2>&1 &
    PROXY_PID=$!

    # 等待代理就绪
    echo "[..] 等待代理就绪..."
    for i in $(seq 1 15); do
        if curl -sf "$PROXY_URL" > /dev/null 2>&1; then
            echo "[OK] 代理已就绪 (PID: $PROXY_PID)"
            break
        fi
        sleep 1
    done

    if ! curl -sf "$PROXY_URL" > /dev/null 2>&1; then
        echo "[FAIL] 代理启动超时，请手动运行: python3 proxyCodex.py"
        exit 1
    fi
fi

# 启动 Codex（支持多种安装路径）
CODEX_PATHS=(
    "/Applications/Codex.app"
    "$HOME/Applications/Codex.app"
    "/Applications/Codex CLI.app"
)

CODEX_OPENED=false
for path in "${CODEX_PATHS[@]}"; do
    if [ -d "$path" ]; then
        echo "[OK] 启动 Codex: $path"
        open "$path"
        CODEX_OPENED=true
        break
    fi
done

# 检查 CLI 版本
if ! $CODEX_OPENED && command -v codex &>/dev/null; then
    echo "[OK] 检测到 Codex CLI，请手动运行: codex"
    CODEX_OPENED=true
fi

if ! $CODEX_OPENED; then
    echo "[WARN] 未找到 Codex 应用，请手动启动"
    echo "       代理已在后台运行 (端口 3000)"
    echo "       停止代理: kill $PROXY_PID"
fi

echo ""
echo "========================================"
echo "  Codex 已启动，选择「国内 API 代理」即可使用"
echo "  停止代理: kill $PROXY_PID"
echo "  查看日志: cat /tmp/proxyCodex.log"
echo "========================================"
