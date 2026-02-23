#!/Users/moonshot/项目/youtube/venv/bin/python3.12
"""YouTube to MP3 downloader with embedded metadata (title, artist, cover art)."""

import argparse
import sys
import os

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import yt_dlp


def read_urls(filepath):
    """Read URLs from a text file, one per line. Ignores empty lines and # comments."""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


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

    if not args.no_archive:
        ydl_opts["download_archive"] = os.path.join(args.output, ".archive.txt")

    if args.proxy:
        ydl_opts["proxy"] = args.proxy

    if args.limit_rate:
        ydl_opts["ratelimit"] = args.limit_rate

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
    print(f"  Archive:   {'yes' if not args.no_archive else 'no'}")
    if args.proxy:
        print(f"  Proxy:     {args.proxy}")
    if args.limit_rate:
        print(f"  Rate limit: {args.limit_rate} bytes/s")

    download(urls, args)
    print("\nDone.")


if __name__ == "__main__":
    main()
