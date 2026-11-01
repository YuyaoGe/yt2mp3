#!/usr/bin/env python3
"""Cut meaningless tails off talk recordings: trailing silence, and outro music
after the last spoken sentence.

The cut point is the earlier of:
  A. the start of a silence that runs all the way to the end of the file;
  B. just after the last real Chinese lyric line, when everything after it is
     only English (song lyrics) or nothing at all.
Audio is cut without re-encoding; tags and cover are kept, and lyric lines past
the cut are dropped. Files need embedded lyrics (run transcribe.py first) for B.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
LRC = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
CJK = re.compile(r"[\u4e00-\u9fff]")
OTHER_SCRIPT = re.compile(r"[\u0900-\u0dff\u0e00-\u0eff\u3040-\u30ff\uac00-\ud7af]")


def trailing_silence(path, length, noise_db, min_len):
    """Start of the silence that lasts until EOF, or None."""
    err = subprocess.run(
        [FFMPEG, "-nostats", "-i", path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    if not starts:
        return None
    # Open-ended last silence, or one that ends within a second of EOF
    if len(ends) < len(starts) or ends[-1] >= length - 1.0:
        return starts[-1]
    return None


def parse_lyrics(text):
    out = []
    for line in text.splitlines():
        m = LRC.match(line.strip())
        if m:
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip(), line))
    return out


def is_speech(text):
    """A line that looks like something the speaker actually said."""
    from transcribe import BOILERPLATE
    return (len(CJK.findall(text)) >= 4 and not OTHER_SCRIPT.search(text)
            and not BOILERPLATE.search(text))


def speech_indices(lines):
    out = []
    for i, (t, text, _) in enumerate(lines):
        if not is_speech(text):
            continue
        # Whisper sometimes echoes the tail of the previous sentence over outro music
        if out and t - lines[out[-1]][0] > 10 and text.rstrip("，。") in lines[out[-1]][1]:
            continue
        out.append(i)
    return out


def after_last_speech(lines, length, min_tail):
    """Cut point B: a little after the last spoken line, if only junk follows."""
    idx = max(speech_indices(lines), default=None)
    if idx is None:
        return None
    start, text, _ = lines[idx]
    # LRC has no end times; allow ~0.3 s per character plus padding
    end = start + max(2.0, 0.3 * len(text)) + 2.0
    if idx + 1 < len(lines):
        end = min(end, lines[idx + 1][0] + 0.5) if lines[idx + 1][0] > start + 1 else end
    return end if length - end >= min_tail else None


def cut_file(path, cut, dry_run, backup=None):
    audio = MP3(path, ID3=ID3)
    tags = audio.tags
    if dry_run:
        return
    if backup:
        dest = os.path.join(backup, os.path.basename(os.path.dirname(os.path.abspath(path))))
        os.makedirs(dest, exist_ok=True)
        if not os.path.exists(os.path.join(dest, os.path.basename(path))):
            shutil.copy2(path, dest)
    fd, tmp = tempfile.mkstemp(suffix=".mp3", dir=os.path.dirname(path))
    os.close(fd)
    try:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-map", "0:a",
                        "-c", "copy", "-t", f"{cut:.2f}", "-map_metadata", "-1", tmp],
                       check=True)
        frames = tags.getall("USLT")
        if frames:
            kept = [raw for t, _, raw in parse_lyrics(str(frames[0])) if t < cut]
            lang = frames[0].lang
            tags.delall("USLT")
            tags.add(USLT(encoding=3, lang=lang, desc="", text="\n".join(kept)))
        tags.save(tmp, v2_version=3)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def mmss(s):
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("paths", nargs="+", help="MP3 files or folders")
    p.add_argument("--also", action="append", default=[],
                   help="folder holding copies with the same file names (e.g. the _small "
                        "versions); they get the same cut. Repeatable.")
    p.add_argument("--min-trim", type=float, default=15,
                   help="only cut if at least this many seconds go (default 15)")
    p.add_argument("--noise", type=float, default=-60, help="silence threshold in dB (default -60)")
    p.add_argument("--silence-only", action="store_true",
                   help="only cut trailing silence, not outro music")
    p.add_argument("--dry-run", action="store_true", help="report cuts without changing files")
    p.add_argument("--backup", metavar="DIR",
                   help="copy each file here (in a subfolder named after its folder) before cutting")
    args = p.parse_args()

    files = []
    for x in args.paths:
        files += sorted(glob.glob(os.path.join(x, "*.mp3"))) if os.path.isdir(x) else [x]
    if not files:
        sys.exit("No MP3 files found")

    total = n = 0
    for path in files:
        audio = MP3(path, ID3=ID3)
        length = audio.info.length
        frames = audio.tags.getall("USLT") if audio.tags else []
        lines = parse_lyrics(str(frames[0])) if frames else []
        source = str(audio.tags.get("TXXX:lyrics_source", "")) if audio.tags else ""
        if "OCR" in source:
            # Lyrics came from on-screen subtitles because the audio is silent;
            # silence tells us nothing here
            print(f"  {os.path.basename(path)[:34]:36s} skipped (lyrics from OCR, audio is silent)")
            continue

        cuts = []
        a = trailing_silence(path, length, args.noise, 2)
        if a is not None:
            cuts.append((a + 1.0, "静音"))
        if not args.silence_only and lines:
            b = after_last_speech(lines, length, args.min_trim)
            if b is not None:
                cuts.append((b, "片尾音乐/无语音"))
        if not cuts:
            continue
        cut, why = min(cuts)
        if length - cut < args.min_trim:
            continue
        if cut < max(30, length * 0.2):
            print(f"  {os.path.basename(path)[:34]:36s} skipped (cut at {mmss(cut)} would drop "
                  f"most of the file; check it by hand)")
            continue

        last = next((t for t in reversed(lines) if t[0] < cut and is_speech(t[1])), None)
        print(f"  {os.path.basename(path)[:34]:36s} {mmss(length)} -> {mmss(cut)}  "
              f"(-{int(length - cut)}s, {why})  last: {last[1][:24] if last else '-'}")
        cut_file(path, cut, args.dry_run, args.backup)
        for d in args.also:
            twin = os.path.join(d, os.path.basename(path))
            if os.path.exists(twin):
                cut_file(twin, cut, args.dry_run, args.backup)
        total += length - cut
        n += 1

    verb = "would cut" if args.dry_run else "cut"
    print(f"\n{verb} {mmss(total)} from {n}/{len(files)} file(s)")


if __name__ == "__main__":
    main()
