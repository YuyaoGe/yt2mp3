#!/usr/bin/env python3
"""Transcribe audio files with Whisper (MLX) and embed the result as synced lyrics."""

import argparse
import glob
import multiprocessing
import os
import re
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT, ID3NoHeaderError

MODELS = {
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
}


def has_lyrics(filepath):
    try:
        audio = MP3(filepath, ID3=ID3)
    except Exception:
        return False
    return bool(audio.tags and audio.tags.getall("USLT"))


def seconds_to_lrc(seconds):
    """Format a timestamp in seconds as an LRC tag [MM:SS.xx]."""
    total_min = int(seconds // 60)
    sec = seconds - total_min * 60
    return f"[{total_min:02d}:{sec:05.2f}]"


SPLIT_AFTER = "。！？；!?;…"
SPLIT_SOFT = "，、,"
MAX_CHARS = 28
MIN_CHARS = 8

CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"
# Whisper sometimes writes 什么 with the rare variant 幺, which OpenCC leaves alone
VARIANTS = [(re.compile("([什怎这那多要甚])[幺麽]"), lambda m: m.group(1) + "么")]
# It also punctuates Chinese with ASCII marks; only the ones following a
# Chinese character are safe to widen, so "1,000" and "3.5" survive
HALFWIDTH = {",": "，", "?": "？", "!": "！", ";": "；", ":": "："}
PUNCT = re.compile(f"(?<=[{CJK}])([,?!;:])")


def polish(text):
    for pattern, repl in VARIANTS:
        text = pattern.sub(repl, text)
    return PUNCT.sub(lambda m: HALFWIDTH[m.group(1)], text)


def split_text(text):
    """Break a long line at punctuation into chunks small enough to read at a glance."""
    if len(text) <= MAX_CHARS:
        return [text]

    chunks = []
    buf = ""
    for i, ch in enumerate(text):
        buf += ch
        hard = ch in SPLIT_AFTER
        soft = ch in SPLIT_SOFT and len(buf) >= MAX_CHARS
        if (hard or soft) and len(buf) >= MIN_CHARS:
            chunks.append(buf)
            buf = ""
    if buf:
        if chunks and len(buf) < MIN_CHARS:
            chunks[-1] += buf
        else:
            chunks.append(buf)

    # Nothing to split on: fall back to fixed-width slices
    if len(chunks) == 1 and len(chunks[0]) > MAX_CHARS:
        text = chunks[0]
        chunks = [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)]

    return chunks


def segments_to_lrc(segments, converter=None):
    lines = []
    prev_text = ""
    for seg in segments:
        text = " ".join(seg.get("text", "").split())
        if not text or text == prev_text:
            continue
        prev_text = text
        if converter:
            text = converter.convert(text)
        text = polish(text)

        start, end = seg["start"], seg.get("end", seg["start"])
        chunks = split_text(text)
        if len(chunks) == 1:
            lines.append(f"{seconds_to_lrc(start)}{text}")
            continue

        # Spread the segment's time across chunks in proportion to their length
        span = max(end - start, 0.0)
        total_chars = sum(len(c) for c in chunks)
        offset = 0
        for chunk in chunks:
            ts = start + span * offset / total_chars
            lines.append(f"{seconds_to_lrc(ts)}{chunk}")
            offset += len(chunk)

    return "\n".join(lines)


def embed_lyrics(filepath, lyrics, lang="zho"):
    """Embed lyrics as a USLT tag, replacing any existing one."""
    try:
        audio = MP3(filepath, ID3=ID3)
    except ID3NoHeaderError:
        audio = MP3(filepath)
        audio.add_tags()

    audio.tags.delall("USLT")
    audio.tags.add(USLT(encoding=3, lang=lang, desc="", text=lyrics))
    audio.save()


def make_converter(variant):
    if variant == "auto":
        return None
    import opencc

    # The "p" variants also swap region-specific wording, not just glyphs
    return opencc.OpenCC("s2twp" if variant == "trad" else "tw2sp")


def convert_existing(filepath, converter):
    """Rewrite the lyrics already embedded in a file, without re-transcribing."""
    audio = MP3(filepath, ID3=ID3)
    frames = audio.tags.getall("USLT") if audio.tags else []
    if not frames:
        return 0

    lines = str(frames[0]).splitlines()
    converted = []
    for line in lines:
        ts, sep, text = line.partition("]")
        if sep and ts.startswith("["):
            converted.append(f"{ts}]{polish(converter.convert(text))}")
        else:
            converted.append(polish(converter.convert(line)))

    embed_lyrics(filepath, "\n".join(converted), frames[0].lang)
    return len(converted)


def format_duration(seconds):
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


def install_shutdown_handler():
    """Take the worker processes down with us, otherwise they keep holding the GPU."""

    def shutdown(signum, frame):
        for child in multiprocessing.active_children():
            child.terminate()
        sys.exit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, shutdown)


def transcribe_one(task):
    """Transcribe a single file and embed the lyrics. Runs in a worker process."""
    filepath, opts = task
    name = os.path.basename(filepath)
    audio_len = MP3(filepath).info.length
    t0 = time.time()

    import mlx_whisper

    try:
        result = mlx_whisper.transcribe(
            filepath,
            path_or_hf_repo=MODELS[opts["model"]],
            language=opts["language"],
            initial_prompt=opts["prompt"],
            verbose=None,
        )
    except Exception as e:
        return {"name": name, "ok": False, "msg": f"Error: {e}"}

    lyrics = segments_to_lrc(result.get("segments", []), make_converter(opts["zh_variant"]))
    if not lyrics:
        return {"name": name, "ok": False, "msg": "No speech detected"}

    lang = result.get("language", opts["language"] or "")
    embed_lyrics(filepath, lyrics, "zho" if lang.startswith("zh") else "eng")

    if opts["save_lrc"]:
        with open(os.path.splitext(filepath)[0] + ".lrc", "w", encoding="utf-8") as f:
            f.write(lyrics + "\n")

    elapsed = time.time() - t0
    return {
        "name": name,
        "ok": True,
        "msg": f"{len(lyrics.splitlines())} lines, {format_duration(audio_len)} audio "
               f"in {format_duration(elapsed)} ({audio_len / elapsed:.0f}x realtime, {lang})",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Whisper and embed synced lyrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s output/
  %(prog)s output/ -m large -l zh -t 4
  %(prog)s output/ --zh-variant trad --save-lrc
  %(prog)s "output/one file.mp3" --force
""",
    )

    parser.add_argument("target", help="directory of audio files, or a single file")
    parser.add_argument("-m", "--model", default="turbo", choices=list(MODELS),
                        help="Whisper model size (default: turbo)")
    parser.add_argument("-l", "--language", default=None,
                        help="spoken language code, e.g. zh / en (default: auto-detect)")
    parser.add_argument("--zh-variant", default="auto", choices=["auto", "trad", "simp"],
                        help="convert Chinese output to Traditional/Simplified (default: auto = leave as-is)")
    parser.add_argument("--prompt", default=None,
                        help="initial prompt to steer style and punctuation")
    parser.add_argument("--save-lrc", action="store_true",
                        help="also write a .lrc file next to each audio file")
    parser.add_argument("--force", action="store_true",
                        help="re-transcribe files that already have lyrics")
    parser.add_argument("--convert-only", action="store_true",
                        help="only apply --zh-variant to lyrics that are already embedded, "
                             "no transcription")
    parser.add_argument("-t", "--threads", type=int, default=3,
                        help="concurrent worker processes (default: 3). Each holds its own "
                             "copy of the model, roughly 3GB of memory per worker")

    args = parser.parse_args()

    if args.threads < 1:
        print("Error: --threads must be at least 1")
        sys.exit(1)

    if os.path.isdir(args.target):
        files = sorted(glob.glob(os.path.join(args.target, "*.mp3")))
    elif os.path.isfile(args.target):
        files = [args.target]
    else:
        print(f"Error: not found: {args.target}")
        sys.exit(1)

    if not files:
        print(f"No mp3 files found in {args.target}")
        sys.exit(1)

    if args.convert_only:
        if args.zh_variant == "auto":
            print("Error: --convert-only needs --zh-variant trad or simp")
            sys.exit(1)
        converter = make_converter(args.zh_variant)
        changed = 0
        for filepath in files:
            lines = convert_existing(filepath, converter)
            if lines:
                changed += 1
                print(f"  {os.path.basename(filepath)}: {lines} lines -> {args.zh_variant}")
        print(f"\nConverted {changed}/{len(files)} file(s)")
        return

    pending = files if args.force else [f for f in files if not has_lyrics(f)]
    skipped = len(files) - len(pending)

    print(f"Found {len(files)} file(s)")
    print(f"  Model:     {args.model} ({MODELS[args.model]})")
    print(f"  Language:  {args.language or 'auto-detect'}")
    print(f"  Variant:   {args.zh_variant}")
    print(f"  Save .lrc: {'yes' if args.save_lrc else 'no'}")
    print(f"  Workers:   {args.threads}")
    if skipped:
        print(f"Skipped {skipped} that already have lyrics")
    if not pending:
        print("Nothing to do.")
        return

    opts = {
        "model": args.model,
        "language": args.language,
        "prompt": args.prompt,
        "zh_variant": args.zh_variant,
        "save_lrc": args.save_lrc,
    }

    # Longest files first, so the tail of the run is not one straggler
    pending.sort(key=lambda f: MP3(f).info.length, reverse=True)

    total = len(pending)
    workers = min(args.threads, total)
    failed = []
    started = time.time()

    install_shutdown_handler()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(transcribe_one, (f, opts)): f for f in pending}
        for done, future in enumerate(as_completed(futures), 1):
            res = future.result()
            print(f"[{done}/{total}] {res['name']}\n  {res['msg']}", flush=True)
            if not res["ok"]:
                failed.append(res["name"])

    print(f"\nDone. {total - len(failed)}/{total} transcribed "
          f"in {format_duration(time.time() - started)}")
    if failed:
        print(f"Failed ({len(failed)}):")
        for name in failed:
            print(f"  {name}")


if __name__ == "__main__":
    main()
