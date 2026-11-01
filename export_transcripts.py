#!/usr/bin/env python3
"""Export the lyrics embedded in a folder of MP3s as readable Markdown transcripts.

One file per episode plus an index.md. LRC fragments are joined back into
paragraphs, with a [mm:ss] marker at the start of each so a reader can jump to
the spot in the audio.
"""

import argparse
import glob
import os
import re
import sys

from mutagen.mp3 import MP3
from mutagen.id3 import ID3

LRC = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
END = "。！？…!?"
PUNCT = END + "，、；：,;:”’）)》"
CJK = r"\u4e00-\u9fff"
# Channel branding and stray format codes left in YouTube titles
TITLE_NOISE = re.compile(r"【[^】]*】|\s+(ev|f\d{3})\s*$")

PARA_GAP = 4.0      # a pause this long (s) starts a new paragraph
PARA_CHARS = 260    # ...and so does a paragraph that has grown this long


def mmss(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def parse_lrc(text, drop_latin=True):
    from transcribe import MAX_CHARS, scrub
    raw = []
    for line in text.splitlines():
        m = LRC.match(line.strip())
        if m and m.group(3).strip():
            raw.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))

    # transcribe.py hard-wraps unpunctuated runs at exactly MAX_CHARS, which can
    # cut a word (or an English lyric) in two. Glue those pieces back first, so
    # the filters below see whole sentences.
    merged = []
    for t, body in raw:
        if merged and len(merged[-1][2]) == MAX_CHARS:
            start, joined, _ = merged[-1]
            merged[-1] = (start, joined + body, body)
        else:
            merged.append((t, body, body))

    out = []
    for t, body, _ in merged:
        body = scrub(body)
        if body and not (drop_latin and is_latin(body)):
            out.append((t, body))
    return out


def is_latin(text):
    """A line with no Chinese, or one that is mostly English. In a Chinese talk
    that is almost always background music Whisper transcribed, not the speaker."""
    cjk = len(re.findall(f"[{CJK}]", text))
    letters = sum(c.isascii() and c.isalpha() for c in text)
    return cjk == 0 or (letters >= 6 and letters > cjk * 2.5)


def tidy(fragment):
    # Whisper marks short pauses inside a line with a space; between Chinese
    # characters that reads better as a comma
    return re.sub(f"(?<=[{CJK}])\\s+(?=[{CJK}])", "，", fragment)


def paragraphs(lines):
    paras, buf, start, last = [], "", None, None
    for t, text in lines:
        text = tidy(text)
        if buf and (t - last > PARA_GAP or len(buf) >= PARA_CHARS):
            paras.append((start, buf))
            buf = ""
        if not buf:
            start = t
        elif buf[-1] not in PUNCT:
            buf += "，"
        buf += text
        last = t
    if buf:
        paras.append((start, buf))
    # Close each paragraph with a full stop rather than a dangling comma
    return [(t, p[:-1] + "。" if p[-1] in "，、,"
             else p if p[-1] in PUNCT else p + "。") for t, p in paras]


def clean_title(raw, converter):
    title = TITLE_NOISE.sub("", raw).strip()
    if converter:
        title = converter.convert(title)
    m = re.match(r"^(\d+)\s*(.*)$", title)
    num, name = (int(m.group(1)), m.group(2).strip()) if m else (None, title)
    return num, name


def safe_name(text):
    return re.sub(r"[\\/:*?\"<>|？！：，。、\s]+", "-", text).strip("-")[:60]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("source", help="folder of MP3s with embedded lyrics")
    p.add_argument("output", help="folder to write transcripts/ and index.md into")
    p.add_argument("--course", required=True, help="course name, used in headings")
    p.add_argument("--speaker", default="", help="default speaker name, shown in each header")
    p.add_argument("--speaker-map", default="",
                   help='per-episode speakers, e.g. "8,9,10=Alice;11,13=Bob (guest)"')
    p.add_argument("--title-map", default="",
                   help='replace episode titles, e.g. "9=A clearer title for episode 9"')
    p.add_argument("--zh-variant", choices=["auto", "simp", "trad"], default="simp",
                   help="script for titles (lyrics are already converted at transcription)")
    p.add_argument("--keep-latin", action="store_true",
                   help="keep all-English lines (by default they are dropped as background-music "
                        "lyrics; use this for English-language courses)")
    p.add_argument("--sequence", default="",
                   help='for titles without a leading number: comma-separated title prefixes in '
                        'course order, e.g. "Theory,Practice,Case". Episodes are sorted by group, then by '
                        'the numbers inside the title, and numbered 1..N')
    args = p.parse_args()

    files = sorted(glob.glob(os.path.join(args.source, "*.mp3")))
    if not files:
        sys.exit(f"No MP3s in {args.source}")

    from transcribe import make_converter
    converter = make_converter(args.zh_variant)

    speakers = {}
    for part in filter(None, args.speaker_map.split(";")):
        nums, _, name = part.partition("=")
        for n in nums.split(","):
            speakers[int(n)] = name.strip()
    titles = {}
    for part in filter(None, args.title_map.split(";")):
        n, _, name = part.partition("=")
        titles[int(n)] = name.strip()

    out_dir = os.path.join(args.output, "transcripts")
    os.makedirs(out_dir, exist_ok=True)

    records = []
    for path in files:
        audio = MP3(path, ID3=ID3)
        tags = audio.tags
        raw_title = str(tags.get("TIT2", os.path.splitext(os.path.basename(path))[0]))
        if args.sequence:
            title = TITLE_NOISE.sub("", raw_title).strip()
            num, name = None, converter.convert(title) if converter else title
        else:
            num, name = clean_title(raw_title, converter)
        records.append([num, name, path, audio, tags])

    if args.sequence:
        groups = [g.strip() for g in args.sequence.split(",") if g.strip()]
        # Within a group, compare the numbers in the title: "Case04 part2" < "Case04 part3" < "Case05"
        def key(rec):
            name = rec[1]
            group = next((i for i, g in enumerate(groups) if name.startswith(g)), len(groups))
            nums = [int(n) for n in re.findall(r"\d+", name)]
            return group, nums, name
        records.sort(key=key)
        for i, rec in enumerate(records, 1):
            rec[0] = i

    episodes = []
    for num, name, path, audio, tags in records:
        name = titles.get(num, name)
        url = str(tags.get("TXXX:purl", "")) or str(tags.get("TXXX:comment", ""))
        source = str(tags.get("TXXX:lyrics_source", "")) or "Whisper 语音转写"
        frames = tags.getall("USLT")
        lines = parse_lrc(str(frames[0]), not args.keep_latin) if frames else []

        stem = f"{num:02d}-{safe_name(name)}" if num is not None else safe_name(name)
        rel = f"transcripts/{stem}.md"
        chars = sum(len(t) for _, t in lines)

        body = [f"# {args.course} {num:02d}｜{name}" if num is not None else f"# {args.course}｜{name}", ""]
        speaker = speakers.get(num, args.speaker)
        meta = [("课程", args.course)]
        if speaker:
            meta.append(("讲者", speaker))
        meta += [("集数", f"第 {num} 集" if num is not None else "—"),
                 ("时长", mmss(audio.info.length)),
                 ("来源", url or "—"),
                 ("文字来源", f"{source}，机器生成，可能有同音字或识别错误")]
        body += [f"- **{k}**：{v}" for k, v in meta] + ["", "---", ""]
        if lines:
            body += [f"**[{mmss(t)}]** {para}\n" for t, para in paragraphs(lines)]
        else:
            body.append("_（本集没有可用的文字稿）_")

        with open(os.path.join(args.output, rel), "w", encoding="utf-8") as f:
            f.write("\n".join(body).rstrip() + "\n")
        episodes.append((num if num is not None else 999, name, rel, audio.info.length, chars, url, source, speaker))
        print(f"  {rel}  ({chars} chars)")

    episodes.sort()
    total = sum(e[3] for e in episodes)
    index = [f"# {args.course}｜文字稿目录", "",
             f"共 {len(episodes)} 集，总时长 {mmss(total)}，约 {sum(e[4] for e in episodes) // 1000} 千字。", "",
             "| 集 | 标题 | 讲者 | 时长 | 字数 | 文字来源 | 原视频 |",
             "|---|---|---|---|---|---|---|"]
    for num, name, rel, length, chars, url, source, speaker in episodes:
        n = f"{num:02d}" if num != 999 else "—"
        link = f"[YouTube]({url})" if url else "—"
        index.append(f"| {n} | [{name}]({rel}) | {speaker or '—'} | {mmss(length)} | {chars} | {source} | {link} |")
    with open(os.path.join(args.output, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index) + "\n")
    print(f"\n{len(episodes)} transcripts + index.md -> {args.output}")


if __name__ == "__main__":
    main()
