#!/bin/bash
# ============================================================
# 语音转文字并嵌入同步歌词脚本
# 修改下方参数后运行: bash run_transcribe.sh
# ============================================================

# --- 可修改参数 ---
TARGET_DIR="output"             # 要处理的目录 (也可写单个文件路径)
MODEL="turbo"                   # 模型: turbo / large / medium / small
LANGUAGE="zh"                   # 语言代码 (zh/en/ja...)，留空则自动识别
ZH_VARIANT="simp"               # 中文字形: auto(不转换) / trad(繁体) / simp(简体)
PROMPT=""                       # 引导词，留空则不使用。填入内容涉及的人名、地名、专业术语
                                # 可明显减少同音字错误，例如:
                                # PROMPT="以下是天文科普：哈勃望远镜、系外行星、红移、暗物质。"
                                # 注意: 引导词用什么字形，模型就倾向输出什么字形
SAVE_LRC="no"                   # 是否额外导出 .lrc 文件 (yes/no)
FORCE="no"                      # 是否重新转写已有歌词的文件 (yes/no)
THREADS="3"                     # 并发进程数 (1 = 单进程)
                                # 每个进程独占一份模型，显存与统一内存消耗随之线性增长
                                # 音频较短(20 分钟内)时可上调; 处理长音频时开太多会换页反而更慢
# ------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/venv/bin/python3.12"
SCRIPT="${SCRIPT_DIR}/transcribe.py"

if [ ! -e "${SCRIPT_DIR}/${TARGET_DIR}" ] && [ ! -e "${TARGET_DIR}" ]; then
    echo "Error: ${TARGET_DIR} not found"
    exit 1
fi

TARGET="${SCRIPT_DIR}/${TARGET_DIR}"
[ ! -e "${TARGET}" ] && TARGET="${TARGET_DIR}"

echo "========================================"
echo "  Whisper Transcribe -> Synced Lyrics"
echo "========================================"
echo "  Target:    ${TARGET_DIR}"
echo "  Model:     ${MODEL}"
echo "  Language:  ${LANGUAGE:-auto}"
echo "  Variant:   ${ZH_VARIANT}"
echo "  Save .lrc: ${SAVE_LRC}"
echo "  Force:     ${FORCE}"
echo "  Workers:   ${THREADS}"
echo "========================================"
echo ""

# 构建参数
ARGS=("${TARGET}")
ARGS+=(-m "${MODEL}")
ARGS+=(--zh-variant "${ZH_VARIANT}")
ARGS+=(-t "${THREADS}")

[ -n "${LANGUAGE}" ]     && ARGS+=(-l "${LANGUAGE}")
[ -n "${PROMPT}" ]       && ARGS+=(--prompt "${PROMPT}")
[ "${SAVE_LRC}" = "yes" ] && ARGS+=(--save-lrc)
[ "${FORCE}" = "yes" ]    && ARGS+=(--force)

"${PYTHON}" "${SCRIPT}" "${ARGS[@]}"
