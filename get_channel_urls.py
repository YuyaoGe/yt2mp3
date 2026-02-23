#!/Users/moonshot/项目/youtube/venv/bin/python3.12
"""Extract all video URLs from a YouTube channel and write to a text file."""

import argparse
import sys
import os

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import yt_dlp


def get_channel_videos(channel_url, cookies_file=None, browser=None, proxy=None, max_count=0):
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "cookiefile": None if browser else cookies_file,
        "cookiesfrombrowser": (browser,) if browser else None,
        "remote_components": ["ejs:github"],
    }

    if proxy:
        ydl_opts["proxy"] = proxy

    if max_count > 0:
        ydl_opts["playlistend"] = max_count

    urls = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if not info:
            return urls
        entries = info.get("entries", [])
        for entry in entries:
            if entry and entry.get("url"):
                urls.append(f"https://www.youtube.com/watch?v={entry['id']}")
    return urls


def main():
    parser = argparse.ArgumentParser(
        description="Extract all video URLs from a YouTube channel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s https://www.youtube.com/@ChannelName -o channel_urls.txt
  %(prog)s https://www.youtube.com/@ChannelName -o urls.txt -n 50
  %(prog)s https://www.youtube.com/channel/UCxxxxxx -o urls.txt --proxy socks5://127.0.0.1:1080
""",
    )

    parser.add_argument("channel", help="YouTube channel URL (@name or /channel/UCxxx)")
    parser.add_argument("-o", "--output", default="channel_urls.txt",
                        help="output file for URLs (default: channel_urls.txt)")
    parser.add_argument("-c", "--cookies", default="cookies.txt",
                        help="Netscape format cookies file (default: cookies.txt)")
    parser.add_argument("-b", "--browser", default=None,
                        choices=["safari", "chrome", "firefox", "edge", "brave", "opera", "chromium"],
                        help="read cookies directly from browser (e.g. safari). Overrides --cookies")
    parser.add_argument("-n", "--max-count", type=int, default=0,
                        help="max number of videos to extract (default: 0 = all)")
    parser.add_argument("--proxy", default=None,
                        help="proxy URL (e.g. socks5://127.0.0.1:1080)")

    args = parser.parse_args()

    if not args.browser and not os.path.isfile(args.cookies):
        print(f"Error: cookies file not found: {args.cookies}")
        sys.exit(1)

    print(f"Extracting video URLs from: {args.channel}")
    print(f"  Cookies:   {args.browser + ' browser' if args.browser else args.cookies}")
    if args.max_count > 0:
        print(f"  Max videos: {args.max_count}")

    urls = get_channel_videos(args.channel, args.cookies, args.browser, args.proxy, args.max_count)

    if not urls:
        print("No videos found.")
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")

    print(f"Found {len(urls)} video(s). Written to {args.output}")


if __name__ == "__main__":
    main()
