#!/usr/bin/env python3
"""Recover lyrics from subtitles burned into the picture, for videos whose audio is silent.

Runs ocr_frames.swift (macOS Vision) over the bottom band of the video, keeps the
centred subtitle line, collapses the frames a line stays on screen into one LRC
entry, and embeds the result in the matching MP3 like transcribe.py would.
"""

import argparse
import difflib
import os
import subprocess
import sys
from collections import Counter

from transcribe import embed_lyrics, make_converter, polish, scrub, seconds_to_lrc

HERE = os.path.dirname(os.path.abspath(__file__))
OCR = os.path.join(HERE, "ocr_frames.swift")


def run_ocr(video, step, top, start=None, end=None):
    cmd = ["swift", OCR, video, str(step), str(top)]
    if start is not None:
        cmd += [str(start), str(end if end is not None else 1e9)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"OCR failed:\n{out.stderr[-2000:]}")
    for line in out.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) == 5:
            t, cx, w, conf, text = parts
            yield float(t), float(cx), float(w), float(conf), text.strip()


def pick_subtitles(boxes, centre, tolerance, min_conf):
    """One subtitle string per sampled time: the confident box sitting on the centre line."""
    per_time = {}
    for t, cx, w, conf, text in boxes:
        if conf < min_conf or abs(cx - centre) > tolerance or not text:
            continue
        # Several boxes can share a frame (two-line subs); keep them left to right
        per_time.setdefault(t, []).append((cx - w / 2, text))
    return {t: "".join(s for _, s in sorted(v)) for t, v in per_time.items()}


def same_line(a, b):
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def group(samples, step):
    """Collapse consecutive frames showing the same line into (start, text)."""
    entries = []
    run_start, run_texts, last_t = None, [], None
    for t in sorted(samples):
        text = samples[t]
        gap = last_t is not None and t - last_t > step * 2.5
        if run_texts and (gap or not same_line(run_texts[-1], text)):
            entries.append((run_start, Counter(run_texts).most_common(1)[0][0]))
            run_texts = []
        if not run_texts:
            run_start = t
        run_texts.append(text)
        last_t = t
    if run_texts:
        entries.append((run_start, Counter(run_texts).most_common(1)[0][0]))
    return entries


def mark_source(mp3, source):
    """Record where the lyrics came from, so exports can tell OCR from speech-to-text."""
    from mutagen.id3 import ID3, TXXX
    tags = ID3(mp3)
    tags.delall("TXXX:lyrics_source")
    tags.add(TXXX(encoding=3, desc="lyrics_source", text=source))
    tags.save(mp3)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("video", help="local video file with burned-in subtitles")
    p.add_argument("mp3", help="MP3 to embed the lyrics into")
    p.add_argument("--step", type=float, default=0.5, help="seconds between sampled frames (default 0.5)")
    p.add_argument("--top", type=float, default=0.82,
                   help="subtitle band starts at this fraction of frame height (default 0.82)")
    p.add_argument("--centre", type=float, default=0.5,
                   help="horizontal centre of the subtitle line, 0-1 (default 0.5)")
    p.add_argument("--tolerance", type=float, default=0.04,
                   help="how far a box centre may sit from --centre (default 0.04)")
    p.add_argument("--min-conf", type=float, default=0.5, help="drop OCR boxes below this confidence")
    p.add_argument("--zh-variant", choices=["auto", "trad", "simp"], default="simp")
    p.add_argument("--save-lrc", action="store_true", help="also write a .lrc next to the MP3")
    p.add_argument("--dry-run", action="store_true", help="print the LRC instead of embedding it")
    p.add_argument("--range", nargs=2, type=float, metavar=("START", "END"),
                   help="only OCR this stretch, in seconds (for trying settings)")
    args = p.parse_args()

    for path in (args.video, args.mp3):
        if not os.path.isfile(path):
            sys.exit(f"Error: not found: {path}")

    start, end = args.range if args.range else (None, None)
    boxes = list(run_ocr(args.video, args.step, args.top, start, end))
    samples = pick_subtitles(boxes, args.centre, args.tolerance, args.min_conf)
    entries = group(samples, args.step)

    converter = make_converter(args.zh_variant)
    lines = []
    for t, text in entries:
        if converter:
            text = converter.convert(text)
        text = scrub(polish(text))
        if text:
            lines.append(f"{seconds_to_lrc(t)}{text}")
    lyrics = "\n".join(lines)

    print(f"{len(boxes)} OCR boxes, {len(samples)} frames with a subtitle, {len(lines)} lines")
    if not lines:
        sys.exit("No subtitles found; try a different --top or --centre")
    if args.dry_run:
        print(lyrics)
        return

    embed_lyrics(args.mp3, lyrics)
    mark_source(args.mp3, "画面硬字幕识别（OCR）")
    if args.save_lrc:
        with open(os.path.splitext(args.mp3)[0] + ".lrc", "w", encoding="utf-8") as f:
            f.write(lyrics + "\n")
    print(f"Embedded into {args.mp3}")


if __name__ == "__main__":
    main()
