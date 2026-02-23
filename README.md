# yt2mp3

[中文版](README_zh.md)

Batch download an entire YouTube channel as MP3 files — with cover art, metadata, and synchronized lyrics, all embedded automatically.

## Why yt2mp3?

- **One command, entire channel** — Extract all video URLs from any YouTuber, then batch convert to MP3
- **Music-ready files** — Every MP3 comes with title, artist, album, year, cover art, and time-synced lyrics (LRC) baked into the file, ready for any music player
- **Zero manual cookies** — Reads login cookies directly from your browser (Safari/Chrome/Firefox), no extensions or export steps needed
- **Fast & resumable** — Multi-threaded downloads (3 threads by default); built-in archive skips already-downloaded files across runs
- **Robust fallbacks** — If yt-dlp's built-in metadata or thumbnail embedding fails, custom fallback processors retry automatically

## Quick Start

### Step 1: Extract all video URLs from a channel

Edit `run_get_urls.sh` — set `CHANNEL_URL` to your target channel:

```bash
CHANNEL_URL="https://www.youtube.com/@YourFavoriteChannel"
```

Run it:

```bash
bash run_get_urls.sh
```

This produces a `channel_urls.txt` file containing all video URLs from that channel.

### Step 2: Batch download as MP3

Copy or rename the URL file to `input.txt` (or edit `INPUT_FILE` in the script):

```bash
cp channel_urls.txt input.txt
bash run_download.sh
```

Done. All videos are downloaded as MP3 files into the `output/` directory, complete with metadata, cover art, and lyrics.

## Requirements

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/) (required by yt-dlp for YouTube JS challenge solving)
- YouTube login session in your browser

## Installation

```bash
git clone https://github.com/YuyaoGe/yt2mp3.git
cd yt2mp3

python3.12 -m venv venv
source venv/bin/activate
pip install yt-dlp mutagen

# macOS
brew install ffmpeg deno
```

## Project Structure

```
yt2mp3/
├── run_get_urls.sh       # Step 1: extract channel video URLs (edit config & run)
├── get_channel_urls.py   # URL extraction logic
├── run_download.sh       # Step 2: batch download as MP3 (edit config & run)
├── yt2mp3.py             # Download & conversion logic
├── input.txt             # Your URL list (one per line, # for comments)
└── output/               # Downloaded MP3 files land here
```

**Typical workflow:** `run_get_urls.sh` -> `input.txt` -> `run_download.sh` -> `output/`

You only need to edit the shell scripts and run them. The `.py` files handle everything under the hood.

## Configuration

Both shell scripts have a clearly-marked configuration section at the top. Open them in any text editor and adjust as needed.

### run_get_urls.sh

```bash
CHANNEL_URL="https://www.youtube.com/@ChannelName"   # Target channel
OUTPUT_FILE="channel_urls.txt"                        # Output file
COOKIES_FROM_BROWSER="safari"    # Browser to read cookies from (or leave empty to use file)
COOKIES_FILE="cookies.txt"      # Fallback: Netscape-format cookies file
MAX_COUNT="0"                   # Max videos to extract (0 = all)
PROXY=""                        # Proxy URL (e.g. socks5://127.0.0.1:1080)
```

### run_download.sh

```bash
INPUT_FILE="input.txt"          # URL list file
COOKIES_FROM_BROWSER="safari"   # Browser to read cookies from
COOKIES_FILE="cookies.txt"     # Fallback cookies file
OUTPUT_DIR="output"            # Output directory
QUALITY="128"                  # Bitrate: 64/96/128/192/256/320 kbps
FORMAT="mp3"                   # Format: mp3/m4a/opus/flac/wav
NAMING="%(title)s"             # Filename template
EMBED_METADATA="yes"           # Embed title, artist, album, year
EMBED_THUMBNAIL="yes"          # Embed cover art
EMBED_LYRICS="yes"             # Embed synchronized lyrics
SUBS_LANG="zh-Hans,zh,en"     # Subtitle language preference
USE_ARCHIVE="yes"              # Skip already-downloaded files
THREADS="3"                    # Concurrent download threads
PROXY=""                       # Proxy URL
LIMIT_RATE=""                  # Download rate limit (bytes/s)
```

## Advanced: Direct CLI Usage

You can also call the Python scripts directly for more control:

```bash
# Extract URLs
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -b safari -o urls.txt -n 50

# Download
python3 yt2mp3.py urls.txt -b safari -q 320 -t 5 -o music/
python3 yt2mp3.py urls.txt -b chrome -f m4a --no-lyrics
python3 yt2mp3.py urls.txt -c cookies.txt --proxy socks5://127.0.0.1:1080
```

Run `python3 yt2mp3.py --help` or `python3 get_channel_urls.py --help` for full option details.

## What Gets Embedded

Each downloaded MP3 contains:

| Tag | Source | Example |
|-----|--------|---------|
| Title | Video title | `My Song Title` |
| Artist | Channel name | `Artist Name` |
| Album | Channel name | `Artist Name` |
| Year | Upload date | `2024` |
| Cover Art | Video thumbnail | (embedded image) |
| Lyrics | YouTube subtitles | Time-synced LRC format |

## Notes

- On macOS, the first run may prompt for Keychain access to read browser cookies — allow it
- Use `--no-archive` or set `USE_ARCHIVE="no"` to force re-downloading everything
- The download archive (`.archive.txt`) is stored inside the output directory
- Cookies files contain private data — never commit them to version control

## License

MIT
