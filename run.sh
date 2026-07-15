#!/bin/bash
# 简历助手后端服务启动脚本
# 自动设置WeasyPrint所需的macOS动态库路径

set -e

# 检测操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "检测到macOS系统，设置PDF渲染所需的环境变量..."

    # 查找Homebrew安装的pango路径
    PANGO_PATH=$(brew --prefix pango 2>/dev/null || echo "")
    HARFBUZZ_PATH=$(brew --prefix harfbuzz 2>/dev/null || echo "")
    CAIRO_PATH=$(brew --prefix cairo 2>/dev/null || echo "")
    FONTCONFIG_PATH=$(brew --prefix fontconfig 2>/dev/null || echo "")

    # 构建DYLD_LIBRARY_PATH
    LIB_PATHS=""
    [[ -n "$PANGO_PATH" ]] && LIB_PATHS="$LIB_PATHS:$PANGO_PATH/lib"
    [[ -n "$HARFBUZZ_PATH" ]] && LIB_PATHS="$LIB_PATHS:$HARFBUZZ_PATH/lib"
    [[ -n "$CAIRO_PATH" ]] && LIB_PATHS="$LIB_PATHS:$CAIRO_PATH/lib"
    [[ -n "$FONTCONFIG_PATH" ]] && LIB_PATHS="$LIB_PATHS:$FONTCONFIG_PATH/lib"

    if [[ -n "$LIB_PATHS" ]]; then
        export DYLD_LIBRARY_PATH="${LIB_PATHS#:}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
        echo "已设置 DYLD_LIBRARY_PATH"
    fi
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 优先使用本地虚拟环境
if [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [[ -f "/opt/anaconda3/bin/python" ]]; then
    PYTHON="/opt/anaconda3/bin/python"
else
    PYTHON="python3"
fi

echo "使用Python: $PYTHON"

# 启动后端服务
exec "$PYTHON" -m uvicorn mcp_service_simple:app --host 0.0.0.0 --port 8000 --reload --workers 6
