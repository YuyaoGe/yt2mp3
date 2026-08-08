#!/usr/bin/env python3
"""Draw a typographic cover so a player has something to show.

The layout is one an editor would recognise: a letterspaced caption and a hair
rule at the top, the title set flush left and sized to fill the measure, then a
second rule with the author's name hanging off the right margin. Only three
colours are needed; the caption and rules are mixed from them.
"""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

SERIF = "/System/Library/Fonts/Supplemental/Songti.ttc"
LATIN = "/System/Library/Fonts/Supplemental/Baskerville.ttc"
SIZE = 1000
MARGIN = 76
# Large enough that the name still reads when the cover is a thumbnail
AUTHOR_RATIO = 0.86


def blend(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    pair = [(int(a[i:i + 2], 16), int(b[i:i + 2], 16)) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in pair)


def wrap(text, per_line):
    return [text[i:i + per_line] for i in range(0, len(text), per_line)]


def put(draw, xy, text, font, fill, align="left"):
    """Place text by its visual box rather than the font's roomy line box."""
    box = draw.textbbox((0, 0), text, font=font)
    x, y = xy
    if align == "right":
        x -= box[2]
    else:
        x -= box[0]
    draw.text((x, y - box[1]), text, font=font, fill=fill)
    return box[3] - box[1]


def tracked(draw, xy, text, font, fill, space):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + space


def fit(draw, lines, width, height):
    """Largest size at which the longest line fills the measure and all fit."""
    probe = 100
    widest = max(draw.textlength(l, font=ImageFont.truetype(SERIF, probe)) for l in lines)
    size = int(probe * width / widest)
    while size > 8:
        font = ImageFont.truetype(SERIF, size)
        if (max(draw.textlength(l, font=font) for l in lines) <= width
                and size * 1.06 * len(lines) <= height):
            break
        size -= 1
    return size


def main():
    parser = argparse.ArgumentParser(description="Draw an album cover")
    parser.add_argument("title", help="main text, use / to force a line break")
    parser.add_argument("-s", "--subtitle", default="", help="author name")
    parser.add_argument("--caption", default="", help="small latin line at the top")
    parser.add_argument("-o", "--output", required=True, help="output jpeg path")
    parser.add_argument("-c", "--color", default="#f0e9dc", help="background colour")
    parser.add_argument("--ink", default="#25201c", help="title colour")
    parser.add_argument("--accent", default="#a63f2c", help="author colour")
    args = parser.parse_args()

    img = Image.new("RGB", (SIZE, SIZE), args.color)
    draw = ImageDraw.Draw(img)
    faint = blend(args.color, args.ink, 0.45)
    hairline = blend(args.color, args.ink, 0.25)

    lines = []
    for part in args.title.split("/"):
        lines.extend(wrap(part, 6))

    measure = SIZE - 2 * MARGIN
    author_size = 0
    if args.subtitle:
        # Sized against the title, so solve for the title first with a rough cap
        author_size = int(fit(draw, lines, measure, 520) * AUTHOR_RATIO)

    foot = SIZE - MARGIN - author_size
    rule_y = foot - 46 if args.subtitle else SIZE - MARGIN
    top = 214

    size = fit(draw, lines, measure, rule_y - top - 30)
    font = ImageFont.truetype(SERIF, size)
    step = int(size * 1.06)

    if args.caption:
        tracked(draw, (MARGIN, 96), args.caption.upper(),
                ImageFont.truetype(LATIN, 22), faint, 4)
    draw.line([(MARGIN, 152), (SIZE - MARGIN, 152)], fill=hairline, width=2)

    for i, line in enumerate(lines):
        put(draw, (MARGIN, top + i * step), line, font, args.ink)

    if args.subtitle:
        draw.line([(MARGIN, rule_y), (SIZE - MARGIN, rule_y)], fill=hairline, width=2)
        put(draw, (SIZE - MARGIN, foot), args.subtitle,
            ImageFont.truetype(SERIF, author_size), args.accent, "right")

    img.save(args.output, "JPEG", quality=90)
    print(f"{args.output}  {os.path.getsize(args.output) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
