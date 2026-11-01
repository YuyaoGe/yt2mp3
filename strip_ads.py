#!/usr/bin/env python3
"""Drop resold-course adverts and Whisper hallucinations from embedded lyrics."""

import argparse
import glob
import os
import re
import sys

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT

# transcribe.py imports MLX lazily, so pulling in the filter costs nothing
from transcribe import scrub

DEFAULT_PATTERNS = [
    r"\d{9,}",                          # the shop's contact number
    r"请加微信",                         # not "他加微信了", which is ordinary speech
    r"(想要?收听|请订阅)更多.{0,6}节目",
    r"知识福利社",
]
# The advert often spills onto a short trailing line such as "的加入。"
TAIL = re.compile(r"^\[[^\]]*\](的?加入[。.]?|期待您的加入[。.]?)$")

LINE = re.compile(r"^\[[^\]]*\]")


def clean(lines, pattern, hallucinations=True):
    """Return (kept lines, dropped count, trimmed count)."""
    keep = []
    dropped = trimmed = 0
    just_dropped = False
    for line in lines:
        if hallucinations:
            stamp = LINE.match(line)
            prefix = stamp.group(0) if stamp else ""
            text = line[len(prefix):]
            scrubbed = scrub(text)
            if not scrubbed:
                dropped += 1
                continue
            if scrubbed != text:
                trimmed += 1
                line = prefix + scrubbed
        if pattern.search(line):
            dropped += 1
            just_dropped = True
            continue
        if just_dropped and TAIL.match(line):
            dropped += 1
            continue
        just_dropped = False
        keep.append(line)
    return keep, dropped, trimmed


def main():
    parser = argparse.ArgumentParser(
        description="Remove adverts and Whisper hallucinations from embedded lyrics")
    parser.add_argument("target", help="directory of mp3 files, or a single file")
    parser.add_argument("-p", "--pattern", action="append", default=[],
                        help="extra regex marking an advert line (repeatable)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be removed without saving")
    parser.add_argument("--keep-hallucinations", dest="hallucinations", action="store_false",
                        help="only remove adverts, leave Whisper filler "
                             "(looped tokens, stock fan-sub credits) alone")
    args = parser.parse_args()

    if os.path.isdir(args.target):
        files = sorted(glob.glob(os.path.join(args.target, "*.mp3")))
        if not files:
            # A library split into one folder per album
            files = sorted(glob.glob(os.path.join(args.target, "**", "*.mp3"),
                                     recursive=True))
    elif os.path.isfile(args.target):
        files = [args.target]
    else:
        print(f"Error: not found: {args.target}")
        sys.exit(1)

    pattern = re.compile("|".join(DEFAULT_PATTERNS + args.pattern))

    touched = total_dropped = total_trimmed = 0
    for path in files:
        audio = MP3(path, ID3=ID3)
        frames = audio.tags.getall("USLT") if audio.tags else []
        if not frames:
            continue

        lines = str(frames[0]).splitlines()
        keep, dropped, trimmed = clean(lines, pattern, args.hallucinations)
        if not (dropped or trimmed):
            continue

        touched += 1
        total_dropped += dropped
        total_trimmed += trimmed
        note = f"-{dropped} line(s)" + (f", {trimmed} trimmed" if trimmed else "")
        print(f"  {os.path.basename(path)}: {note}")
        if args.dry_run:
            continue

        lang = frames[0].lang
        audio.tags.delall("USLT")
        audio.tags.add(USLT(encoding=3, lang=lang, desc="", text="\n".join(keep)))
        audio.save()

    verb = "would remove" if args.dry_run else "removed"
    print(f"\n{verb} {total_dropped} line(s) and trimmed {total_trimmed} "
          f"from {touched}/{len(files)} file(s)")


if __name__ == "__main__":
    main()
