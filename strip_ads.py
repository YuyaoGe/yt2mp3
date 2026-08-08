#!/usr/bin/env python3
"""Drop resold-course adverts from embedded lyrics."""

import argparse
import glob
import os
import re
import sys

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT

DEFAULT_PATTERNS = [
    r"\d{9,}",                          # the shop's contact number
    r"请加微信",                         # not "他加微信了", which is ordinary speech
    r"(想要?收听|请订阅)更多.{0,6}节目",
    r"知识福利社",
]
# The advert often spills onto a short trailing line such as "的加入。"
TAIL = re.compile(r"^\[[^\]]*\](的?加入[。.]?|期待您的加入[。.]?)$")

LINE = re.compile(r"^\[[^\]]*\]")


def clean(lines, pattern):
    keep = []
    dropped = 0
    just_dropped = False
    for line in lines:
        if pattern.search(line):
            dropped += 1
            just_dropped = True
            continue
        if just_dropped and TAIL.match(line):
            dropped += 1
            continue
        just_dropped = False
        keep.append(line)
    return keep, dropped


def main():
    parser = argparse.ArgumentParser(description="Remove advert lines from embedded lyrics")
    parser.add_argument("target", help="directory of mp3 files, or a single file")
    parser.add_argument("-p", "--pattern", action="append", default=[],
                        help="extra regex marking an advert line (repeatable)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be removed without saving")
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

    touched = total_dropped = 0
    for path in files:
        audio = MP3(path, ID3=ID3)
        frames = audio.tags.getall("USLT") if audio.tags else []
        if not frames:
            continue

        lines = str(frames[0]).splitlines()
        keep, dropped = clean(lines, pattern)
        if not dropped:
            continue

        touched += 1
        total_dropped += dropped
        print(f"  {os.path.basename(path)}: -{dropped} line(s)")
        if args.dry_run:
            continue

        lang = frames[0].lang
        audio.tags.delall("USLT")
        audio.tags.add(USLT(encoding=3, lang=lang, desc="", text="\n".join(keep)))
        audio.save()

    verb = "would remove" if args.dry_run else "removed"
    print(f"\n{verb} {total_dropped} line(s) from {touched}/{len(files)} file(s)")


if __name__ == "__main__":
    main()
