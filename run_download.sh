#!/bin/bash
# ============================================================
# YouTube to MP3 下载脚本
# 修改下方参数后运行: bash run_download.sh
# ============================================================

# --- 可修改参数 ---
INPUT_FILE="input.txt"          # 包含 YouTube 链接的文件
COOKIES_FILE="cookies.txt"      # Netscape 格式 cookies 文件
OUTPUT_DIR="output"             # MP3 输出目录
QUALITY="128"                   # 音频比特率 (64, 96, 128, 192, 256, 320)
FORMAT="mp3"                    # 音频格式 (mp3, m4a, opus, flac, wav)
NAMING="%(title)s"              # 文件命名模板 (可用: %(title)s, %(channel)s, %(id)s, %(upload_date)s)
EMBED_METADATA="yes"            # 是否嵌入元数据 (yes/no)
EMBED_THUMBNAIL="yes"           # 是否嵌入封面图 (yes/no)
EMBED_LYRICS="yes"              # 是否嵌入歌词/字幕 (yes/no)
SUBS_LANG="zh-Hans,zh,en"      # 字幕语言偏好，逗号分隔 (优先取前面的语言)
USE_ARCHIVE="yes"               # 是否启用下载记录，跳过已下载 (yes/no)
PROXY=""                        # 代理地址，留空则不使用 (例: socks5://127.0.0.1:1080)
LIMIT_RATE=""                   # 下载限速 bytes/s，留空则不限速 (例: 1000000 = ~1MB/s)
# ------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/venv/bin/python3.12"
SCRIPT="${SCRIPT_DIR}/yt2mp3.py"

if [ ! -f "${SCRIPT_DIR}/${INPUT_FILE}" ]; then
    echo "Error: ${INPUT_FILE} not found"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/${COOKIES_FILE}" ]; then
    echo "Error: ${COOKIES_FILE} not found"
    exit 1
fi

URL_COUNT=$(grep -cv '^\s*#\|^\s*$' "${SCRIPT_DIR}/${INPUT_FILE}")
echo "========================================"
echo "  YouTube -> Audio Downloader"
echo "========================================"
echo "  Input:     ${INPUT_FILE} (${URL_COUNT} URLs)"
echo "  Cookies:   ${COOKIES_FILE}"
echo "  Output:    ${OUTPUT_DIR}/"
echo "  Quality:   ${FORMAT} @ ${QUALITY}kbps"
echo "  Metadata:  ${EMBED_METADATA}"
echo "  Thumbnail: ${EMBED_THUMBNAIL}"
echo "  Lyrics:    ${EMBED_LYRICS} (${SUBS_LANG})"
echo "  Archive:   ${USE_ARCHIVE}"
[ -n "${PROXY}" ]      && echo "  Proxy:     ${PROXY}"
[ -n "${LIMIT_RATE}" ] && echo "  Rate limit: ${LIMIT_RATE} bytes/s"
echo "========================================"
echo ""

# 构建参数
ARGS=("${SCRIPT_DIR}/${INPUT_FILE}")
ARGS+=(-c "${SCRIPT_DIR}/${COOKIES_FILE}")
ARGS+=(-o "${SCRIPT_DIR}/${OUTPUT_DIR}")
ARGS+=(-q "${QUALITY}")
ARGS+=(-f "${FORMAT}")
ARGS+=(--naming "${NAMING}")

[ "${EMBED_METADATA}" = "no" ]  && ARGS+=(--no-metadata)
[ "${EMBED_THUMBNAIL}" = "no" ] && ARGS+=(--no-thumbnail)
[ "${EMBED_LYRICS}" = "no" ]    && ARGS+=(--no-lyrics)
[ "${EMBED_LYRICS}" != "no" ]   && ARGS+=(--subs-lang "${SUBS_LANG}")
[ "${USE_ARCHIVE}" = "no" ]     && ARGS+=(--no-archive)
[ -n "${PROXY}" ]               && ARGS+=(--proxy "${PROXY}")
[ -n "${LIMIT_RATE}" ]          && ARGS+=(--limit-rate "${LIMIT_RATE}")

"${PYTHON}" "${SCRIPT}" "${ARGS[@]}"
