#!/bin/bash
# ============================================================
#  yt2mp3 - full pipeline
#  Usage:
#    bash run_pipeline.sh            # download -> transcribe -> clean -> trim -> review
#    bash run_pipeline.sh apply R01,S02   # cut the items you picked in the review page
#    bash run_pipeline.sh finish     # compress (+ export transcripts if EXPORT_DIR is set)
#    bash run_pipeline.sh <step>     # run one step: download transcribe clean trim review compress export
# ============================================================

# --- 可修改参数 / Settings ---
INPUT_FILE="input.txt"          # YouTube 链接列表 / URL list
OUTPUT_DIR="output"             # MP3 输出目录 / where the MP3s go
COOKIES_FROM_BROWSER="safari"   # 从浏览器读取 cookies，留空则用 cookies.txt
DL_THREADS="3"                  # 下载并发数
LANGUAGE="zh"                   # 转写语言，留空自动识别
ZH_VARIANT="simp"               # 中文字形: auto / trad / simp
PROMPT=""                       # 转写引导词（人名、术语），可减少同音字
TR_THREADS="3"                  # 转写并发进程数
TRIM_MIN="15"                   # 片尾短于这么多秒就不裁
COMPRESS_KBPS="64"              # 压缩码率，单声道
BACKUP_DIR="_untrimmed_backup"  # 裁剪前的原文件备份位置
EXPORT_DIR=""                   # 设了就把歌词导出成 Markdown 文字稿到这里
EXPORT_TITLE="Transcripts"      # 文字稿标题
# -----------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Personal overrides (not committed): local/run_pipeline.conf, same variable names as above
[ -f "${SCRIPT_DIR}/local/run_pipeline.conf" ] && . "${SCRIPT_DIR}/local/run_pipeline.conf"

PY="${SCRIPT_DIR}/venv/bin/python3"
[ -x "${PY}" ] || PY="python3"
SMALL_DIR="${OUTPUT_DIR}_small"
REVIEW_DIR="review_$(basename "${OUTPUT_DIR}")"
cd "${SCRIPT_DIR}" || exit 1
set -e

step_download() {
    echo "== download"
    local args=("${INPUT_FILE}" -o "${OUTPUT_DIR}" -t "${DL_THREADS}")
    if [ -n "${COOKIES_FROM_BROWSER}" ]; then args+=(-b "${COOKIES_FROM_BROWSER}"); else args+=(-c cookies.txt); fi
    "${PY}" yt2mp3.py "${args[@]}"
}

step_transcribe() {
    echo "== transcribe (files that already have lyrics are skipped)"
    local args=("${OUTPUT_DIR}" -t "${TR_THREADS}" --zh-variant "${ZH_VARIANT}")
    [ -n "${LANGUAGE}" ] && args+=(-l "${LANGUAGE}")
    [ -n "${PROMPT}" ] && args+=(--prompt "${PROMPT}")
    "${PY}" transcribe.py "${args[@]}"
}

step_clean() {
    echo "== clean lyrics (Whisper filler, spoken adverts)"
    "${PY}" strip_ads.py "${OUTPUT_DIR}"
}

step_trim() {
    echo "== trim tails (trailing silence, outro after the last sentence)"
    "${PY}" trim_tail.py "${OUTPUT_DIR}" --min-trim "${TRIM_MIN}" --backup "${BACKUP_DIR}"
}

step_review() {
    echo "== find repeated audio and silence"
    "${PY}" find_repeats.py "${OUTPUT_DIR}" "${REVIEW_DIR}"
    echo
    echo "Listen to the samples in ${REVIEW_DIR}/index.html, then:"
    echo "  bash run_pipeline.sh apply R01,S02     # the IDs you want gone"
    echo "  bash run_pipeline.sh finish"
}

step_apply() {
    [ -n "$1" ] || { echo "usage: bash run_pipeline.sh apply R01,S02"; exit 1; }
    echo "== remove $1"
    "${PY}" find_repeats.py "${OUTPUT_DIR}" "${REVIEW_DIR}" --apply "$1" --backup "${BACKUP_DIR}"
}

step_compress() {
    echo "== compress to ${COMPRESS_KBPS} kbps mono -> ${SMALL_DIR}"
    "${PY}" compress.py "${OUTPUT_DIR}" -o "${SMALL_DIR}" -b "${COMPRESS_KBPS}"
}

step_export() {
    [ -n "${EXPORT_DIR}" ] || { echo "== export skipped (EXPORT_DIR is empty)"; return; }
    echo "== export transcripts -> ${EXPORT_DIR}"
    "${PY}" export_transcripts.py "${OUTPUT_DIR}" "${EXPORT_DIR}" --course "${EXPORT_TITLE}"
}

case "${1:-all}" in
    all)        step_download; step_transcribe; step_clean; step_trim; step_review ;;
    finish)     step_compress; step_export ;;
    apply)      step_apply "$2" ;;
    download|transcribe|clean|trim|review|compress|export) "step_$1" ;;
    *) sed -n '2,9p' "$0"; exit 1 ;;
esac
