# yt2mp3

[中文版](README_zh.md)

Batch download an entire YouTube channel as MP3 files — with cover art, metadata, and synchronized lyrics, all embedded automatically.

## Why yt2mp3?

- **One command, entire channel** — Extract all video URLs from any YouTuber, then batch convert to MP3
- **Music-ready files** — Every MP3 comes with title, artist, album, year, cover art, and time-synced lyrics (LRC) baked into the file, ready for any music player
- **Lyrics even without subtitles** — When a video has no caption track, transcribe the speech locally with Whisper and embed the result as synced lyrics
- **Zero manual cookies** — Reads login cookies directly from your browser (Safari/Chrome/Firefox), no extensions or export steps needed
- **Fast & resumable** — Multi-threaded downloads (3 threads by default); built-in archive skips already-downloaded files across runs
- **Robust fallbacks** — If yt-dlp's built-in metadata or thumbnail embedding fails, custom fallback processors retry automatically
- **Shrink for upload** — Re-encode to a smaller bitrate while preserving every ID3 frame, lyrics and cover art included
- **Clean, not just converted** — Drops Whisper's filler lines, trims silent or musical tails, and finds jingles that repeat across episodes so you can listen and cut them

## The Pipeline

```
URLs ─> download ─> transcribe ─> clean ─> trim ─> review ─> (apply) ─> compress ─> export
        yt2mp3.py   transcribe.py strip_ads trim_tail find_repeats.py    compress.py export_transcripts.py
```

`run_pipeline.sh` runs it end to end. Set the options at the top of the script, put your URLs in `input.txt`, then:

```bash
bash run_pipeline.sh                 # download -> transcribe -> clean -> trim -> review
open review_output/index.html        # listen to the repeated / silent parts it found
bash run_pipeline.sh apply R01,S03   # cut the ones you don't want
bash run_pipeline.sh finish          # compress, and export transcripts if EXPORT_DIR is set
```

Any single step can be run on its own: `bash run_pipeline.sh transcribe`, `... trim`, and so on. Each step only touches what it needs to: already-downloaded videos and already-transcribed files are skipped, and every destructive step keeps a copy of the original in `_untrimmed_backup/`.

| Step | What it does |
|---|---|
| download | One MP3 per video, with title, artist, album, year, cover art and subtitles as synced lyrics |
| transcribe | Whisper (Apple Silicon, MLX) for every file still without lyrics |
| clean | Removes lines Whisper invents over music or silence (stock subtitle credits, a word looped twenty times) and spoken adverts |
| trim | Cuts trailing silence and the outro music after the last spoken sentence; lossless, tags and lyrics kept |
| review | Fingerprints every episode, finds audio that recurs across episodes (intro/outro jingles, inserted promos) plus silent heads, tails and gaps, and writes a page of short samples to listen to |
| apply | Cuts the items you chose from every episode they occur in, anywhere in the file, shifting the lyric timestamps to match |
| compress | 64 kbps mono copies, all tags preserved |
| export | Optional: one Markdown transcript per episode plus an index, paragraphs with `[mm:ss]` stamps |

The step-by-step guide below covers the same tools one at a time.

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

### Step 3 (optional): Fill in missing lyrics with Whisper

Many videos have no caption track at all, so there is nothing to embed. In that case, transcribe the audio locally:

```bash
bash run_transcribe.sh
```

This scans `output/`, skips files that already have lyrics, transcribes the rest with Whisper on the GPU, and embeds the result as time-synced LRC. Long segments are split at punctuation so each line stays short enough to follow while listening.

### Step 4 (optional): Shrink the files

Spoken-word audio does not need 128 kbps stereo. Re-encode to 64 kbps mono and roughly halve the size:

```bash
python3 compress.py output/
```

Output lands in `output_small/`; the originals are left untouched. Tags are copied over with mutagen afterwards — ffmpeg alone would silently drop the lyrics frame — and every file is verified before the script reports success.

## Bonus: cleaning up audio you already have

The transcription and tagging steps do not care where the audio came from. If you
have a folder of downloaded lecture or course files, `organize.py` flattens it into
a library that reads well in a player:

```bash
python3 organize.py "~/Downloads/Some Course" -o "podcast/Some Course" \
    -a "Some Course" --artist "Author" --dry-run
```

It derives an episode number and title from each filename, orders episodes by
their folder and date, and writes clean title/artist/album/track tags. Resold
course files often arrive with a shop's advert in the artist, album and cover art;
the tag block is rebuilt from scratch, so that goes away. Run with `--dry-run`
first to check the names, then drop the flag to copy the files. Sources are never
modified.

`make_cover.py` draws a typographic cover to embed, for when the audio has no
artwork of its own. Give it a title, an author and three colours; the caption
and hair rules are mixed from those, so a set of albums can share one layout
and still be told apart:

```bash
python3 make_cover.py "Some Course/Season 2" -s "Author" \
    --caption "a course in something" -o cover.jpg \
    -c "#f4efe2" --ink "#23201c" --accent "#a63f2c"
```

The same resellers who plant adverts in the tags also read one aloud at the top
and tail of each recording, which then lands in the transcript. `strip_ads.py`
drops those lines from the embedded lyrics:

```bash
python3 strip_ads.py "podcast/Some Course" --dry-run
```

It matches phone numbers and a few stock phrases, and follows an advert onto the
short line it usually spills onto. Check the report with `--dry-run` before
letting it save. It also removes Whisper's hallucinated filler by default
(`--keep-hallucinations` turns that off).

## More tools

**Trim silent or musical tails** — `trim_tail.py` cuts each file at the earlier of
(a) a silence that runs to the end, or (b) just after the last real sentence when
only music follows. Cuts are lossless (`-c copy`), tags and cover are kept, and
lyric lines past the cut are dropped:

```bash
python3 trim_tail.py output/ --dry-run
python3 trim_tail.py output/ --also output_small --backup _untrimmed_backup
```

**Find and remove repeated audio** — `find_repeats.py` fingerprints every file and
cross-correlates every pair, so an intro jingle, a sign-off song or a promo spot
inserted mid-episode is found even when each copy was mixed slightly differently.
It also lists silent heads, tails and long gaps. Nothing is changed until you pick:

```bash
python3 find_repeats.py output/ review/              # writes review/index.html with samples
python3 find_repeats.py output/ review/ --apply R01,S02 --backup _untrimmed_backup
```

**Lyrics from burned-in subtitles** — when a video's audio is silent but the
subtitles are drawn into the picture, `burnin_subs.py` reads them with macOS
Vision OCR (via `ocr_frames.swift`, no extra install) and embeds them as synced
lyrics:

```bash
python3 burnin_subs.py video.mp4 "output/that episode.mp3" --dry-run
```

**Export transcripts** — `export_transcripts.py` turns the embedded lyrics of a
folder into one Markdown file per episode (merged into paragraphs, `[mm:ss]` at
each) plus an `index.md`, for reading or for feeding to other tools:

```bash
python3 export_transcripts.py output/ transcripts/ --course "My Archive"
```

## Requirements

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/)
- [deno](https://deno.land/) (required by yt-dlp for YouTube JS challenge solving)
- YouTube login session in your browser
- Apple Silicon Mac for the transcription step (`mlx-whisper` runs on Metal)

## Installation

```bash
git clone https://github.com/YuyaoGe/yt2mp3.git
cd yt2mp3

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# macOS
brew install ffmpeg deno
```

Transcription downloads the Whisper weights on first use (~1.6 GB for the default `turbo` model) and caches them under `~/.cache/huggingface`.

## Project Structure

```
yt2mp3/
├── run_pipeline.sh       # The whole pipeline in one script (edit config & run)
├── run_get_urls.sh       # Step 1: extract channel video URLs (edit config & run)
├── get_channel_urls.py   # URL extraction logic
├── run_download.sh       # Step 2: batch download as MP3 (edit config & run)
├── yt2mp3.py             # Download & conversion logic
├── run_transcribe.sh     # Step 3: transcribe missing lyrics (edit config & run)
├── transcribe.py         # Whisper transcription -> LRC -> ID3 embedding
├── strip_ads.py          # Drop Whisper filler and spoken adverts from lyrics
├── trim_tail.py          # Cut silent / musical tails
├── find_repeats.py       # Find repeated jingles & silence, review, then cut
├── compress.py           # Step 4: re-encode smaller, keeping all tags
├── export_transcripts.py # Lyrics -> Markdown transcripts + index
├── burnin_subs.py        # Lyrics from subtitles burned into the video (OCR)
├── ocr_frames.swift      # macOS Vision OCR helper for burnin_subs.py
├── organize.py           # Bonus: tidy a folder of audio into a podcast library
├── make_cover.py         # Bonus: draw a cover for audio without artwork
├── local/                # Your own settings (*.conf), git-ignored
├── input.txt             # Your URL list (one per line, # for comments)
├── output/               # Downloaded MP3 files land here
└── output_small/         # Compressed copies land here
```

**Typical workflow:** `run_get_urls.sh` -> `input.txt` -> `run_pipeline.sh` -> listen -> `run_pipeline.sh apply ...` -> `run_pipeline.sh finish`

You only need to edit the shell scripts and run them. The `.py` files handle everything under the hood.

## Configuration

Every shell script has a clearly-marked configuration section at the top. To keep your own values out of git, put them in `local/<script name>.conf` instead (for example `local/run_pipeline.conf` containing `COOKIES_FROM_BROWSER="edge"`); the script reads it after its defaults, and `local/` is git-ignored.

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
SLEEP=""                       # Random pause (SLEEP to 2x SLEEP s) before each video
```

### run_transcribe.sh

```bash
TARGET_DIR="output"             # Directory (or single file) to process
MODEL="turbo"                   # turbo / large / medium / small
LANGUAGE="zh"                   # Spoken language code, empty = auto-detect
ZH_VARIANT="simp"               # Chinese glyphs: auto / trad / simp
PROMPT=""                       # Domain terms to reduce homophone errors
SAVE_LRC="no"                   # Also write .lrc files next to the audio
FORCE="no"                      # Re-transcribe files that already have lyrics
THREADS="3"                     # Concurrent worker processes
```

Two details worth knowing:

- The initial prompt steers spelling *and* script. A prompt written in Traditional Chinese makes the model emit Traditional output, so keep it consistent with `ZH_VARIANT`.
- Already-embedded lyrics can be converted between Simplified and Traditional without re-running the model: `python3 transcribe.py output/ --zh-variant simp --convert-only`.

## Advanced: Direct CLI Usage

You can also call the Python scripts directly for more control:

```bash
# Extract URLs
python3 get_channel_urls.py https://www.youtube.com/@ChannelName -b safari -o urls.txt -n 50

# Download
python3 yt2mp3.py urls.txt -b safari -q 320 -t 5 -o music/
python3 yt2mp3.py urls.txt -b chrome -f m4a --no-lyrics
python3 yt2mp3.py urls.txt -c cookies.txt --proxy socks5://127.0.0.1:1080

# Transcribe
python3 transcribe.py output/ -l zh -t 3
python3 transcribe.py output/ -m large --save-lrc
python3 transcribe.py output/ --zh-variant simp --convert-only

# Compress
python3 compress.py output/ -b 64
python3 compress.py output/ -b 96 --stereo -o output_hq/

# Clean, trim, review
python3 strip_ads.py output/ --dry-run
python3 trim_tail.py output/ --dry-run
python3 find_repeats.py output/ review/ && python3 find_repeats.py output/ review/ --apply R01
```

Every script has a `--help` describing its full option set.

## What Gets Embedded

Each downloaded MP3 contains:

| Tag | Source | Example |
|-----|--------|---------|
| Title | Video title | `My Song Title` |
| Artist | Channel name | `Artist Name` |
| Album | Channel name | `Artist Name` |
| Year | Upload date | `2024` |
| Cover Art | Video thumbnail | (embedded image) |
| Lyrics | YouTube subtitles, or Whisper | Time-synced LRC format |

Lyrics live in the ID3 `USLT` frame as LRC text, so a single `.mp3` carries everything — no sidecar files to keep track of when copying or uploading.

## Notes

- On macOS, the first run may prompt for Keychain access to read browser cookies — allow it
- Safari's cookie store is protected by macOS privacy controls, so a sandboxed terminal may not be able to read it. Export a `cookies.txt` instead and leave `COOKIES_FROM_BROWSER` empty
- YouTube rotates session cookies when it sees many parallel requests from one account. An exported `cookies.txt` is a frozen copy and goes stale after a few dozen videos ("Sign in to confirm you're not a bot"); reading cookies straight from the browser (`-b edge`, `-b chrome`, …) stays fresh because the browser keeps renewing the session
- Some videos offer no audio-only stream. The downloader then takes format 18 (a single 360p file with AAC audio) instead of hundreds of HLS fragments
- If your environment refuses to delete many files in one go, pass `--keep-intermediate` to `yt2mp3.py` and clear the leftover video/thumbnail files yourself
- Use `--no-archive` or set `USE_ARCHIVE="no"` to force re-downloading everything
- The download archive (`.archive.txt`) is stored inside the output directory
- Cookies files contain private data — never commit them to version control

## License

MIT
