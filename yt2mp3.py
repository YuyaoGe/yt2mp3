#!/Users/moonshot/项目/youtube/venv/bin/python3.12
"""YouTube to MP3 downloader with embedded metadata (title, artist, cover art, lyrics)."""

import argparse
import glob
import queue
import re
import sys
import os
import threading

os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

import yt_dlp
import urllib.request

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, USLT, ID3NoHeaderError


def read_urls(filepath):
    """Read URLs from a text file, one per line. Ignores empty lines and # comments."""
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def _extract_video_id(url):
    """Extract YouTube video ID from URL."""
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


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
    pattern = r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*?\n((?:(?!\d{2}:\d{2}:\d{2})(?!\n\n).+\n?)*)"
    entries = re.findall(pattern, content)

    lines = []
    prev_text = ""
    for ts, text_block in entries:
        text = re.sub(r"<[^>]+>", "", text_block).strip()
        text = re.sub(r"^\d+\n", "", text, flags=re.MULTILINE).strip()
        if not text or text == prev_text:
            continue
        prev_text = text

        lrc_ts = _ts_to_lrc(ts)
        if lrc_ts:
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
            id3_lang = "zho" if any(f".{l}." in best for l in ("zh-Hans", "zh")) else "eng"
            embed_lyrics(filepath, lyrics, id3_lang)
            self.to_screen(f"Embedded lyrics ({os.path.basename(best)})")

        for sf in sub_files:
            os.remove(sf)

        return [], info


class ThumbnailFallbackPP(yt_dlp.postprocessor.PostProcessor):
    """Fallback: if EmbedThumbnail failed, download thumbnail via URL and embed with mutagen."""

    def run(self, info):
        filepath = info.get("filepath", "")
        if not filepath.endswith(".mp3"):
            return [], info

        # Check if cover art already exists
        try:
            audio = MP3(filepath, ID3=ID3)
            if audio.tags and audio.tags.getall("APIC"):
                return [], info
        except Exception:
            pass

        thumbnail_url = info.get("thumbnail", "")
        if not thumbnail_url:
            return [], info

        try:
            req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                img_data = resp.read()

            mime = "image/jpeg"
            if thumbnail_url.endswith(".png"):
                mime = "image/png"
            elif thumbnail_url.endswith(".webp"):
                mime = "image/webp"

            try:
                audio = MP3(filepath, ID3=ID3)
            except ID3NoHeaderError:
                audio = MP3(filepath)
                audio.add_tags()

            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img_data))
            audio.save()
            self.to_screen("Embedded thumbnail via fallback")
        except Exception as e:
            self.to_screen(f"Thumbnail fallback failed: {e}")

        return [], info


class MetadataFallbackPP(yt_dlp.postprocessor.PostProcessor):
    """Fill in any ID3 tags that FFmpegMetadata missed (e.g. album = channel name)."""

    def run(self, info):
        filepath = info.get("filepath", "")
        if not filepath.endswith(".mp3"):
            return [], info

        try:
            audio = MP3(filepath, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(filepath)
            audio.add_tags()

        changed = False
        tags = audio.tags

        if not tags.getall("TIT2"):
            title = info.get("title", "")
            if title:
                tags.add(TIT2(encoding=3, text=title))
                changed = True

        if not tags.getall("TPE1"):
            artist = info.get("channel", info.get("uploader", ""))
            if artist:
                tags.add(TPE1(encoding=3, text=artist))
                changed = True

        if not tags.getall("TALB"):
            album = info.get("album", info.get("channel", info.get("uploader", "")))
            if album:
                tags.add(TALB(encoding=3, text=album))
                changed = True

        if not tags.getall("TDRC"):
            upload_date = info.get("upload_date", "")
            if upload_date:
                tags.add(TDRC(encoding=3, text=upload_date[:4]))
                changed = True

        if changed:
            audio.save()
            self.to_screen("Filled missing metadata via fallback")

        return [], info


class ArchiveWriterPP(yt_dlp.postprocessor.PostProcessor):
    """Thread-safe post-processor to record completed downloads in archive."""

    def __init__(self, downloader=None, archive_path=None, archive_set=None, lock=None):
        super().__init__(downloader)
        self._path = archive_path
        self._set = archive_set
        self._lock = lock

    def run(self, info):
        vid_id = info.get("id", "")
        extractor = (info.get("extractor_key") or "youtube").lower()
        entry = f"{extractor} {vid_id}"

        with self._lock:
            if entry not in self._set:
                self._set.add(entry)
                with open(self._path, "a") as f:
                    f.write(entry + "\n")

        return [], info


def _make_ydl_opts(args):
    """Build yt-dlp options dict (without archive — handled by ArchiveWriterPP)."""
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

    opts = {
        "ffmpeg_location": "/opt/homebrew/bin",
        "format": "bestaudio/best",
        "cookiefile": None if args.browser else args.cookies,
        "cookiesfrombrowser": (args.browser,) if args.browser else None,
        "remote_components": ["ejs:github"],
        "writethumbnail": args.thumbnail,
        "postprocessors": postprocessors,
        "outtmpl": os.path.join(args.output, args.naming + ".%(ext)s"),
        "ignoreerrors": True,
        "no_warnings": False,
    }

    if args.lyrics:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = args.subs_lang.split(",")
        opts["subtitlesformat"] = "vtt"

    if args.proxy:
        opts["proxy"] = args.proxy

    if args.limit_rate:
        opts["ratelimit"] = args.limit_rate

    # Suppress progress bars when multi-threaded (they'd interleave)
    if args.threads > 1:
        opts["noprogress"] = True

    return opts


def download(urls, args):
    os.makedirs(args.output, exist_ok=True)

    archive_path = os.path.join(args.output, ".archive.txt")
    archive_lock = threading.Lock()
    print_lock = threading.Lock()

    # Load existing archive
    archive_set = set()
    if not args.no_archive and os.path.isfile(archive_path):
        with open(archive_path, "r") as f:
            archive_set = {line.strip() for line in f if line.strip()}

    # Pre-filter already downloaded URLs by video ID
    pending = []
    for url in urls:
        if not args.no_archive:
            vid_id = _extract_video_id(url)
            if vid_id and f"youtube {vid_id}" in archive_set:
                continue
        pending.append(url)

    skipped = len(urls) - len(pending)
    if skipped:
        print(f"Skipped {skipped} already downloaded")
    if not pending:
        print("All URLs already downloaded.")
        return

    total = len(pending)
    completed = [0]  # mutable counter for threads

    # Fill work queue
    url_q = queue.Queue()
    for i, url in enumerate(pending, 1):
        url_q.put((i, url))

    def worker():
        """Each worker thread owns a persistent yt-dlp instance (JS challenge solved once)."""
        opts = _make_ydl_opts(args)
        with yt_dlp.YoutubeDL(opts) as ydl:
            if args.thumbnail:
                ydl.add_post_processor(
                    ThumbnailFallbackPP(ydl), when="post_process",
                )
            if args.metadata:
                ydl.add_post_processor(
                    MetadataFallbackPP(ydl), when="post_process",
                )
            if not args.no_archive:
                ydl.add_post_processor(
                    ArchiveWriterPP(ydl, archive_path=archive_path,
                                    archive_set=archive_set, lock=archive_lock),
                    when="post_process",
                )
            if args.lyrics:
                ydl.add_post_processor(
                    EmbedLyricsPP(ydl, langs=args.subs_lang.split(",")),
                    when="post_process",
                )

            while True:
                try:
                    i, url = url_q.get_nowait()
                except queue.Empty:
                    break

                with print_lock:
                    print(f"\n[{i}/{total}] Downloading: {url}")

                try:
                    ydl.download([url])
                except Exception as e:
                    with print_lock:
                        print(f"  [{i}] Error: {e}")
                finally:
                    with print_lock:
                        completed[0] += 1
                    url_q.task_done()

    num_threads = min(args.threads, total)
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


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
  %(prog)s input.txt -t 3
""",
    )

    parser.add_argument("urls", help="text file with YouTube URLs (one per line, # for comments)")
    parser.add_argument("-c", "--cookies", default="cookies.txt",
                        help="Netscape format cookies file (default: cookies.txt)")
    parser.add_argument("-b", "--browser", default=None,
                        choices=["safari", "chrome", "firefox", "edge", "brave", "opera", "chromium"],
                        help="read cookies directly from browser (e.g. safari). Overrides --cookies")
    parser.add_argument("-o", "--output", default="output",
                        help="output directory (default: output)")
    parser.add_argument("-q", "--quality", type=int, default=128, choices=[64, 96, 128, 192, 256, 320],
                        help="audio bitrate in kbps (default: 128)")
    parser.add_argument("-f", "--format", default="mp3", choices=["mp3", "m4a", "opus", "flac", "wav"],
                        help="audio format (default: mp3)")
    parser.add_argument("-t", "--threads", type=int, default=3,
                        help="number of concurrent download threads (default: 3)")
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

    if not os.path.isfile(args.urls):
        print(f"Error: file not found: {args.urls}")
        sys.exit(1)

    if not args.browser and not os.path.isfile(args.cookies):
        print(f"Error: file not found: {args.cookies}")
        sys.exit(1)

    urls = read_urls(args.urls)
    if not urls:
        print("No URLs found in file.")
        sys.exit(1)

    print(f"Found {len(urls)} URL(s)")
    print(f"  Cookies:   {args.browser + ' browser' if args.browser else args.cookies}")
    print(f"  Format:    {args.format} @ {args.quality}kbps")
    print(f"  Output:    {args.output}/")
    print(f"  Threads:   {args.threads}")
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
