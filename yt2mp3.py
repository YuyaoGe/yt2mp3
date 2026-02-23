#!/Users/moonshot/项目/youtube/venv/bin/python3.12
"""YouTube to MP3 downloader with embedded metadata (title, artist, cover art, lyrics)."""

import argparse
import glob
import re
import sys
import os

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, USLT, ID3NoHeaderError


def read_urls(filepath):
    """Read URLs from a text file, one per line. Ignores empty lines and # comments."""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def _ts_to_lrc(ts_str):
    """Convert VTT/SRT timestamp (HH:MM:SS.mmm) to LRC format [MM:SS.xx]."""
    m = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", ts_str)
    if not m:
        return None
    h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)[:2]
    total_min = h * 60 + mi
    return f"[{total_min:02d}:{s:02d}.{ms}]"


def parse_subtitles(filepath):
    """Parse VTT/SRT subtitle file into LRC format with timestamps."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove VTT header
    content = re.sub(r"^WEBVTT.*?\n\n", "", content, count=1, flags=re.DOTALL)

    # Extract (timestamp, text) pairs
    # Match: "00:00:01.500 --> 00:00:05.200" followed by text lines
    pattern = r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*?\n((?:(?!\d{2}:\d{2}:\d{2})(?!\n\n).+\n?)*)"
    entries = re.findall(pattern, content)

    lines = []
    prev_text = ""
    for ts, text_block in entries:
        # Clean text: remove HTML/VTT tags, SRT sequence numbers, strip
        text = re.sub(r"<[^>]+>", "", text_block).strip()
        text = re.sub(r"^\d+\n", "", text, flags=re.MULTILINE).strip()
        if not text or text == prev_text:
            continue
        prev_text = text

        lrc_ts = _ts_to_lrc(ts)
        if lrc_ts:
            # Multi-line subtitle: join into single line
            single_line = " ".join(text.split("\n"))
            lines.append(f"{lrc_ts}{single_line}")

    return "\n".join(lines)


def embed_lyrics(mp3_path, lyrics, lang="zho"):
    """Embed lyrics as USLT tag in MP3 file."""
    try:
        audio = MP3(mp3_path, ID3=ID3)
    except ID3NoHeaderError:
        audio = MP3(mp3_path)
        audio.add_tags()

    audio.tags.add(USLT(encoding=3, lang=lang, desc="", text=lyrics))
    audio.save()


class EmbedLyricsPP(yt_dlp.postprocessor.PostProcessor):
    """Post-processor: find downloaded subtitles, embed as lyrics, clean up."""

    def __init__(self, downloader=None, langs=None):
        super().__init__(downloader)
        self._langs = langs or ["zh-Hans", "zh", "en"]

    def run(self, info):
        filepath = info.get("filepath", "")
        if not filepath.endswith(".mp3"):
            return [], info

        base = os.path.splitext(filepath)[0]
        sub_files = glob.glob(glob.escape(base) + "*.vtt") + glob.glob(
            glob.escape(base) + "*.srt"
        )

        if not sub_files:
            return [], info

        # Pick best subtitle: prefer by language order
        best = sub_files[0]
        for lang in self._langs:
            for sf in sub_files:
                if f".{lang}." in sf:
                    best = sf
                    break
            else:
                continue
            break

        lyrics = parse_subtitles(best)
        if lyrics:
            # Detect language from filename for USLT lang tag
            id3_lang = "zho" if any(f".{l}." in best for l in ("zh-Hans", "zh")) else "eng"
            embed_lyrics(filepath, lyrics, id3_lang)
            self.to_screen(f"Embedded lyrics ({os.path.basename(best)})")

        # Clean up all subtitle files
        for sf in sub_files:
            os.remove(sf)

        return [], info


def download(urls, args):
    os.makedirs(args.output, exist_ok=True)

    postprocessors = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": args.format,
            "preferredquality": str(args.quality),
        },
    ]

    if args.metadata:
        postprocessors.append({"key": "FFmpegMetadata"})

    if args.thumbnail:
        postprocessors.append({"key": "EmbedThumbnail"})

    ydl_opts = {
        "ffmpeg_location": "/opt/homebrew/bin",
        "format": "bestaudio/best",
        "cookiefile": args.cookies,
        "remote_components": ["ejs:github"],
        "writethumbnail": args.thumbnail,
        "postprocessors": postprocessors,
        "outtmpl": os.path.join(args.output, args.naming + ".%(ext)s"),
        "ignoreerrors": True,
        "no_warnings": False,
    }

    if args.lyrics:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = args.subs_lang.split(",")
        ydl_opts["subtitlesformat"] = "vtt"

    if not args.no_archive:
        ydl_opts["download_archive"] = os.path.join(args.output, ".archive.txt")

    if args.proxy:
        ydl_opts["proxy"] = args.proxy

    if args.limit_rate:
        ydl_opts["ratelimit"] = args.limit_rate

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        if args.lyrics:
            ydl.add_post_processor(
                EmbedLyricsPP(ydl, langs=args.subs_lang.split(",")), when="post_process"
            )

        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Downloading: {url}")
            try:
                ydl.download([url])
            except Exception as e:
                print(f"  Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube to MP3 downloader with metadata embedding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s input.txt
  %(prog)s input.txt -q 320 -o music/
  %(prog)s input.txt -f m4a --no-metadata --no-thumbnail
  %(prog)s input.txt --proxy socks5://127.0.0.1:1080
  %(prog)s input.txt --naming "%%(channel)s - %%(title)s"
  %(prog)s input.txt --subs-lang zh-Hans,zh,en,ja
""",
    )

    parser.add_argument("urls", help="text file with YouTube URLs (one per line, # for comments)")
    parser.add_argument("-c", "--cookies", default="cookies.txt",
                        help="Netscape format cookies file (default: cookies.txt)")
    parser.add_argument("-o", "--output", default="output",
                        help="output directory (default: output)")
    parser.add_argument("-q", "--quality", type=int, default=128, choices=[64, 96, 128, 192, 256, 320],
                        help="audio bitrate in kbps (default: 128)")
    parser.add_argument("-f", "--format", default="mp3", choices=["mp3", "m4a", "opus", "flac", "wav"],
                        help="audio format (default: mp3)")
    parser.add_argument("--naming", default="%(title)s",
                        help='filename template (default: "%%(title)s"). '
                             'Available: %%(title)s, %%(channel)s, %%(id)s, %%(upload_date)s, etc.')
    parser.add_argument("--no-metadata", dest="metadata", action="store_false",
                        help="skip embedding metadata (title, artist, etc.)")
    parser.add_argument("--no-thumbnail", dest="thumbnail", action="store_false",
                        help="skip embedding thumbnail as cover art")
    parser.add_argument("--no-lyrics", dest="lyrics", action="store_false",
                        help="skip downloading and embedding lyrics/subtitles")
    parser.add_argument("--subs-lang", default="zh-Hans,zh,en",
                        help='subtitle language preference, comma-separated (default: "zh-Hans,zh,en")')
    parser.add_argument("--no-archive", action="store_true",
                        help="disable download archive (re-download everything)")
    parser.add_argument("--proxy", default=None,
                        help="proxy URL (e.g. socks5://127.0.0.1:1080)")
    parser.add_argument("--limit-rate", type=int, default=None, metavar="BYTES",
                        help="max download rate in bytes/sec (e.g. 1000000 for ~1MB/s)")

    args = parser.parse_args()

    for f in (args.urls, args.cookies):
        if not os.path.isfile(f):
            print(f"Error: file not found: {f}")
            sys.exit(1)

    urls = read_urls(args.urls)
    if not urls:
        print("No URLs found in file.")
        sys.exit(1)

    print(f"Found {len(urls)} URL(s)")
    print(f"  Format:    {args.format} @ {args.quality}kbps")
    print(f"  Output:    {args.output}/")
    print(f"  Metadata:  {'yes' if args.metadata else 'no'}")
    print(f"  Thumbnail: {'yes' if args.thumbnail else 'no'}")
    print(f"  Lyrics:    {'yes (' + args.subs_lang + ')' if args.lyrics else 'no'}")
    print(f"  Archive:   {'yes' if not args.no_archive else 'no'}")
    if args.proxy:
        print(f"  Proxy:     {args.proxy}")
    if args.limit_rate:
        print(f"  Rate limit: {args.limit_rate} bytes/s")

    download(urls, args)
    print("\nDone.")


if __name__ == "__main__":
    main()
