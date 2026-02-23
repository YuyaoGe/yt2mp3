#!/bin/bash
# ============================================================
# YouTube 频道视频链接提取脚本
# 修改下方参数后运行: bash run_get_urls.sh
# ============================================================

# --- 可修改参数 ---
CHANNEL_URL="https://www.youtube.com/@ChannelName"   # YouTube 频道地址
OUTPUT_FILE="channel_urls.txt"                        # 输出文件名
COOKIES_FILE="cookies.txt"                            # Netscape 格式 cookies 文件
MAX_COUNT="0"                                         # 最多提取视频数 (0 = 全部)
PROXY=""                                              # 代理地址，留空则不使用 (例: socks5://127.0.0.1:1080)
# ------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/venv/bin/python3.12"
SCRIPT="${SCRIPT_DIR}/get_channel_urls.py"

if [ ! -f "${SCRIPT_DIR}/${COOKIES_FILE}" ]; then
    echo "Error: ${COOKIES_FILE} not found"
    exit 1
fi

echo "========================================"
echo "  YouTube Channel URL Extractor"
echo "========================================"
echo "  Channel:   ${CHANNEL_URL}"
echo "  Output:    ${OUTPUT_FILE}"
echo "  Cookies:   ${COOKIES_FILE}"
[ "${MAX_COUNT}" != "0" ] && echo "  Max count: ${MAX_COUNT}"
[ -n "${PROXY}" ]         && echo "  Proxy:     ${PROXY}"
echo "========================================"
echo ""

# 构建参数
ARGS=("${CHANNEL_URL}")
ARGS+=(-o "${SCRIPT_DIR}/${OUTPUT_FILE}")
ARGS+=(-c "${SCRIPT_DIR}/${COOKIES_FILE}")

[ "${MAX_COUNT}" != "0" ] && ARGS+=(-n "${MAX_COUNT}")
[ -n "${PROXY}" ]         && ARGS+=(--proxy "${PROXY}")

"${PYTHON}" "${SCRIPT}" "${ARGS[@]}"
