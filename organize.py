#!/usr/bin/env python3
"""Flatten a course folder into a clean podcast library: readable names, honest tags."""

import argparse
import os
import re
import shutil
import sys
from collections import Counter

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TRCK, TDRC, TCON, APIC

SEP = "[丨｜|]"
# Publish date, written either as "wj-MMDD" or "YY.MMDD" depending on the series
PREFIX = re.compile(rf"^(?:wj-\s*(?P<md>\d+)|(?P<yy>\d{{2}})\.(?P<md2>\d{{4}})){SEP}?\s*",
                    re.IGNORECASE)
LETTER = re.compile(rf"^(?:第(?P<num>\d+)封信)\s*{SEP}?\s*")
# Side strands of a series, some numbered, some one-offs. Longer names first so
# "问答加餐3" is not read as a plain "问答".
KINDS = ["周末问答", "答读者问", "问答加餐", "周五专题", "特别加餐", "春节加餐",
         "徕卡摄影课", "复习和书单", "元旦彩蛋", "新课邀请", "周末加议", "特别来信",
         "新春特辑",
         "发刊词", "加餐", "彩蛋", "复盘", "解读", "问答"]
SHORTEN = {"周末问答": "问答", "答读者问": "问答", "周五专题": "专题"}
KIND = re.compile(rf"^(?P<kind>{'|'.join(KINDS)})\s*(?P<num>\d*)\s*{SEP}?\s*")
# Several series number episodes plainly, e.g. "wj-0103丨40丨标题"
PLAIN = re.compile(rf"^(?P<num>\d{{1,3}})\s*{SEP}\s*")
# "wj-0924丨000丨发刊词｜..." repeats a section number before the real label
SECTION = re.compile(rf"^0{{2,3}}{SEP}\s*")


def parse(stem):
    """Split a source filename into (year, date, label, title)."""
    rest = stem
    year = date = ""

    # A handful of files stamp the date twice, as "wj-0817丨23.0817丨..."
    while (m := PREFIX.match(rest)):
        date = m.group("md") or m.group("md2")
        year = m.group("yy") or year
        rest = rest[m.end():]

    rest = SECTION.sub("", rest)

    # "第001封信·元旦彩蛋丨..." keeps the letter number, the aside goes in the title
    m = LETTER.match(rest)
    if m:
        return year, date, m.group("num").zfill(3), rest[m.end():].lstrip("·丨｜| ")

    m = KIND.match(rest)
    if m:
        kind = SHORTEN.get(m.group("kind"), m.group("kind"))
        num = m.group("num")
        return year, date, kind + (num.zfill(2) if num else ""), rest[m.end():]

    m = PLAIN.match(rest)
    if m:
        return year, date, m.group("num").zfill(2), rest[m.end():]

    # The handbook numbers its own chapters as "wj-01丨标题"
    if date and len(date) <= 2:
        return year, date, date.zfill(2), rest

    return year, date, "", rest


def clean_title(title):
    title = title.strip().strip("·丨｜|：: ")
    return re.sub(r"\s+", " ", title)


def new_name(label, title):
    title = clean_title(title)
    return f"{label}. {title}" if label else title


def collect(source, skip_dirs=()):
    """Gather files in listening order.

    Some series date their files as YY.MMDD, which sorts on its own. The rest
    carry only MM-DD, so a plain date sort would put January ahead of the
    previous October; there the folders make the year explicit, with month
    folders running chronologically by name and the loose files at the top
    forming the final stretch.
    """
    entries = []
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
        group = os.path.relpath(root, source)
        # The root holds the most recent episodes, so it sorts after the folders
        rank = (1, "") if group == "." else (0, group)
        for name in sorted(files):
            if not name.lower().endswith(".mp3"):
                continue
            year, date, label, title = parse(os.path.splitext(name)[0])
            # A whole batch can share the launch date; the opener still comes first
            key = (rank, year, date.zfill(4) if date else "9999",
                   "0" if label == "发刊词" else "1", label, name)
            entries.append((key, date, label, title, os.path.join(root, name)))

    entries.sort(key=lambda e: e[0])
    return [e[1:] for e in entries]


def write_tags(path, title, artist, album, track, total, year, cover):
    try:
        audio = MP3(path, ID3=ID3)
    except ID3NoHeaderError:
        audio = MP3(path)
    # A few files arrive with no tag block at all
    if audio.tags is None:
        audio.add_tags()

    # The source files carry a reseller's ad in the artist, album and cover art
    audio.tags.clear()
    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    audio.tags.add(TRCK(encoding=3, text=f"{track}/{total}"))
    audio.tags.add(TCON(encoding=3, text="Podcast"))
    if year:
        audio.tags.add(TDRC(encoding=3, text=year))
    if cover:
        audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
    audio.save()


def main():
    parser = argparse.ArgumentParser(
        description="Flatten a course folder into a clean podcast library")
    parser.add_argument("source", help="folder to read (searched recursively)")
    parser.add_argument("-o", "--output", required=True, help="destination folder")
    parser.add_argument("-a", "--album", required=True, help="album name")
    parser.add_argument("--artist", default="", help="artist name")
    parser.add_argument("--year", default="", help="year tag")
    parser.add_argument("--cover", default="", help="jpeg file to embed as cover art")
    parser.add_argument("--skip-dir", action="append", default=[],
                        help="subfolder to leave out (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="only print the new names")

    args = parser.parse_args()

    if not os.path.isdir(args.source):
        print(f"Error: not a directory: {args.source}")
        sys.exit(1)

    entries = collect(args.source, skip_dirs=set(args.skip_dir))
    if not entries:
        print(f"No mp3 files found in {args.source}")
        sys.exit(1)

    cover = b""
    if args.cover:
        with open(args.cover, "rb") as f:
            cover = f.read()

    names = [new_name(label, title) for _, label, title, _ in entries]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    unlabeled = [n for (d, label, t, s), n in zip(entries, names) if not label]

    print(f"{len(entries)} file(s) from {args.source}")
    if dupes:
        print(f"\nDuplicate names ({len(dupes)}):")
        for n in dupes:
            print(f"  {n}")
    if unlabeled:
        print(f"\nNo number could be derived ({len(unlabeled)}):")
        for n in unlabeled:
            print(f"  {n}")

    if args.dry_run:
        print("\nNew names:")
        for n in names:
            print(f"  {n}.mp3")
        return

    os.makedirs(args.output, exist_ok=True)
    total = len(entries)
    for i, ((date, label, title, src), name) in enumerate(zip(entries, names), 1):
        dst = os.path.join(args.output, f"{name}.mp3")
        shutil.copy2(src, dst)
        write_tags(dst, clean_title(title) or name, args.artist, args.album,
                   i, total, args.year, cover)
        print(f"[{i}/{total}] {name}", flush=True)

    print(f"\nDone. {total} file(s) in {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
