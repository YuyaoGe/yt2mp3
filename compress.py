#!/usr/bin/env python3
"""Re-encode audio to a smaller size, keeping all ID3 tags (lyrics and cover art included)."""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError


def copy_tags(src, dst):
    """ffmpeg drops frames like USLT, so move the original tag block over wholesale."""
    try:
        tags = ID3(src)
    except ID3NoHeaderError:
        return

    try:
        audio = MP3(dst, ID3=ID3)
    except ID3NoHeaderError:
        audio = MP3(dst)
        audio.add_tags()

    audio.tags.clear()
    for frame in tags.values():
        audio.tags.add(frame)
    audio.save()


def compress_one(task):
    src, dst, bitrate, channels = task
    name = os.path.basename(src)
    before = os.path.getsize(src)

    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-i", src,
        "-vn",  # cover art is restored from the tags afterwards
        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", "-ac", str(channels),
        dst,
    ]

    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"name": name, "ok": False,
                "msg": f"ffmpeg failed: {proc.stderr.strip().splitlines()[-1:]}"}

    try:
        copy_tags(src, dst)
    except Exception as e:
        return {"name": name, "ok": False, "msg": f"tag copy failed: {e}"}

    after = os.path.getsize(dst)
    return {
        "name": name,
        "ok": True,
        "msg": f"{before / 1048576:.1f} MB -> {after / 1048576:.1f} MB "
               f"({100 - after * 100 / before:.0f}% smaller, {time.time() - t0:.0f}s)",
    }


def verify(src, dst):
    """Confirm the re-encoded file kept its lyrics, cover art and title."""
    problems = []
    try:
        a, b = ID3(src), ID3(dst)
    except ID3NoHeaderError:
        return problems
    for frame, label in (("USLT", "lyrics"), ("APIC", "cover"), ("TIT2", "title")):
        if a.getall(frame) and not b.getall(frame):
            problems.append(f"missing {label}")
    if a.getall("USLT") and b.getall("USLT"):
        if len(str(a.getall("USLT")[0])) != len(str(b.getall("USLT")[0])):
            problems.append("lyrics text differs")
    return problems


def main():
    parser = argparse.ArgumentParser(
        description="Re-encode audio smaller while keeping all metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s output/
  %(prog)s output/ -b 32 -o output_tiny/
  %(prog)s output/ --stereo -b 96
""",
    )

    parser.add_argument("source", help="directory of mp3 files to compress")
    parser.add_argument("-o", "--output", default="output_small",
                        help="output directory (default: output_small)")
    parser.add_argument("-b", "--bitrate", type=int, default=64,
                        help="target bitrate in kbps (default: 64)")
    parser.add_argument("--stereo", action="store_true",
                        help="keep stereo (default: downmix to mono, speech does not need stereo)")
    parser.add_argument("-t", "--threads", type=int, default=6,
                        help="concurrent ffmpeg processes (default: 6)")

    args = parser.parse_args()

    if not os.path.isdir(args.source):
        print(f"Error: not a directory: {args.source}")
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg not found")
        sys.exit(1)

    files = sorted(glob.glob(os.path.join(args.source, "*.mp3")))
    if not files:
        print(f"No mp3 files found in {args.source}")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    channels = 2 if args.stereo else 1

    total_before = sum(os.path.getsize(f) for f in files)
    print(f"Found {len(files)} file(s), {total_before / 1048576:.0f} MB total")
    print(f"  Target:    {args.bitrate} kbps {'stereo' if args.stereo else 'mono'}")
    print(f"  Output:    {args.output}/")
    print(f"  Workers:   {args.threads}")

    tasks = [(f, os.path.join(args.output, os.path.basename(f)), args.bitrate, channels)
             for f in files]

    failed = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.threads) as pool:
        futures = {pool.submit(compress_one, t): t for t in tasks}
        for done, future in enumerate(as_completed(futures), 1):
            res = future.result()
            print(f"[{done}/{len(tasks)}] {res['name']}\n  {res['msg']}", flush=True)
            if not res["ok"]:
                failed.append(res["name"])

    print("\nVerifying tags...")
    tag_problems = []
    for src, dst, _, _ in tasks:
        if not os.path.exists(dst):
            continue
        problems = verify(src, dst)
        if problems:
            tag_problems.append((os.path.basename(dst), problems))

    total_after = sum(os.path.getsize(os.path.join(args.output, os.path.basename(f)))
                      for f in files if os.path.exists(os.path.join(args.output, os.path.basename(f))))

    print(f"\nDone in {time.time() - started:.0f}s. "
          f"{total_before / 1048576:.0f} MB -> {total_after / 1048576:.0f} MB "
          f"({100 - total_after * 100 / total_before:.0f}% smaller)")
    print(f"Output: {os.path.abspath(args.output)}")

    if failed:
        print(f"\nFailed ({len(failed)}):")
        for name in failed:
            print(f"  {name}")
    if tag_problems:
        print(f"\nTag problems ({len(tag_problems)}):")
        for name, problems in tag_problems:
            print(f"  {name}: {', '.join(problems)}")
    if not failed and not tag_problems:
        print("All files kept their lyrics, cover art and metadata.")


if __name__ == "__main__":
    main()
