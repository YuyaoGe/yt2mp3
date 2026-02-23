# yt2mp3

[中文版](README_zh.md)

A command-line tool for batch downloading YouTube videos as MP3 with full metadata embedding.

## Features

- Batch download YouTube videos as MP3 (or m4a/opus/flac/wav)
- Multi-threaded concurrent downloads (default: 3 threads)
- Auto-embed metadata: title, artist, album, year, cover art, synchronized lyrics (LRC)
- Read cookies directly from browser (Safari, Chrome, Firefox, etc.) — no manual export needed
- Extract all video URLs from a YouTube channel
- Configurable quality, naming template, proxy, rate limit, and more
- Download archive: skip already-downloaded files

## Requirements

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/) (required by yt-dlp for YouTube JS challenge solving)
- YouTube login session in your browser (or a Netscape-format cookies file)

## Installation

```bash
# Clone
git clone https://github.com/YuyaoGe/yt2mp3.git
cd yt2mp3

# Create virtual environment and install dependencies
python3.12 -m venv venv
source venv/bin/activate
pip install yt-dlp mutagen

# Install system dependencies (macOS)
brew install ffmpeg deno
```

## Usage

### 1. Download YouTube Videos as MP3

Create an `input.txt` file with one YouTube URL per line (`#` for comments):

```
# My playlist
https://www.youtube.com/watch?v=xxxxx
https://www.youtube.com/watch?v=yyyyy
```

Run the shell script (reads cookies from Safari by default):

```bash
bash run_download.sh
```

Or call the Python script directly:

```bash
# Using browser cookies (recommended)
python3 yt2mp3.py input.txt -b safari

# Using cookies file
python3 yt2mp3.py input.txt -c cookies.txt
```

#### Full Options

```
usage: yt2mp3.py [-h] [-c COOKIES] [-b BROWSER] [-o OUTPUT] [-q QUALITY]
                 [-f FORMAT] [-t THREADS] [--naming NAMING] [--no-metadata]
                 [--no-thumbnail] [--no-lyrics] [--subs-lang SUBS_LANG]
                 [--no-archive] [--proxy PROXY] [--limit-rate BYTES]
                 urls

  urls                  text file with YouTube URLs (one per line)
  -c, --cookies         Netscape format cookies file (default: cookies.txt)
  -b, --browser         read cookies from browser: safari, chrome, firefox,
                        edge, brave, opera, chromium. Overrides --cookies
  -o, --output          output directory (default: output)
  -q, --quality         audio bitrate in kbps: 64/96/128/192/256/320 (default: 128)
  -f, --format          audio format: mp3/m4a/opus/flac/wav (default: mp3)
  -t, --threads         concurrent download threads (default: 3)
  --naming              filename template (default: "%(title)s")
                        Available: %(title)s, %(channel)s, %(id)s, %(upload_date)s
  --no-metadata         skip embedding metadata (title, artist, album, year)
  --no-thumbnail        skip embedding cover art
  --no-lyrics           skip downloading and embedding lyrics/subtitles
  --subs-lang           subtitle language preference, comma-separated
                        (default: "zh-Hans,zh,en")
  --no-archive          disable download archive (re-download everything)
  --proxy               proxy URL (e.g. socks5://127.0.0.1:1080)
  --limit-rate          max download rate in bytes/sec
```

### 2. Extract Channel Video URLs

```bash
# Edit CHANNEL_URL in run_get_urls.sh, then:
bash run_get_urls.sh

# Or call directly:
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -b safari -o urls.txt
```

## Shell Script Configuration

Both `run_download.sh` and `run_get_urls.sh` have a configuration section at the top. Edit the variables directly:

```bash
# run_download.sh
COOKIES_FROM_BROWSER="safari"    # Read cookies from browser (leave empty to use file)
COOKIES_FILE="cookies.txt"      # Fallback cookies file
OUTPUT_DIR="output"
QUALITY="128"
FORMAT="mp3"
NAMING="%(title)s"
EMBED_METADATA="yes"
EMBED_THUMBNAIL="yes"
EMBED_LYRICS="yes"
SUBS_LANG="zh-Hans,zh,en"
USE_ARCHIVE="yes"
THREADS="3"
PROXY=""
LIMIT_RATE=""
```

## How It Works

1. **Download**: yt-dlp downloads the best audio stream from YouTube
2. **Convert**: FFmpeg extracts/converts audio to the target format and bitrate
3. **Metadata**: FFmpegMetadata writes basic tags; `MetadataFallbackPP` fills any gaps (title, artist, album from channel name, year)
4. **Cover art**: yt-dlp's EmbedThumbnail embeds the thumbnail; `ThumbnailFallbackPP` retries via direct URL download if needed
5. **Lyrics**: YouTube subtitles are downloaded, parsed into synchronized LRC format, and embedded as USLT ID3 tags
6. **Archive**: Each completed download is recorded in `.archive.txt` (thread-safe) to skip on future runs

## Notes

- The first run on macOS may prompt for Keychain access when reading browser cookies — allow it
- Use `--no-archive` to force re-downloading all files
- Cookies files contain private data — never commit them to version control
- The download archive is per-output-directory (`.archive.txt` inside the output folder)

## License

MIT
