#!/usr/bin/env python3
"""Draw a plain typographic cover so a player has something to show."""

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
SIZE = 1000


def wrap(text, per_line):
    return [text[i:i + per_line] for i in range(0, len(text), per_line)]


def main():
    parser = argparse.ArgumentParser(description="Draw a simple album cover")
    parser.add_argument("title", help="main text, use / to force a line break")
    parser.add_argument("-s", "--subtitle", default="", help="smaller text below")
    parser.add_argument("-o", "--output", required=True, help="output jpeg path")
    parser.add_argument("-c", "--color", default="#1c2b3a", help="background colour")
    args = parser.parse_args()

    img = Image.new("RGB", (SIZE, SIZE), args.color)
    draw = ImageDraw.Draw(img)

    lines = []
    for part in args.title.split("/"):
        lines.extend(wrap(part, 6))

    font_size = 150 if max(len(l) for l in lines) <= 5 else 120
    font = ImageFont.truetype(FONT, font_size)
    small = ImageFont.truetype(FONT, 46)

    gap = int(font_size * 1.32)
    block = gap * len(lines)
    top = (SIZE - block) // 2 - (40 if args.subtitle else 0)

    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        draw.text(((SIZE - w) / 2, top + i * gap), line, font=font, fill="#f5f2ea")

    if args.subtitle:
        w = draw.textlength(args.subtitle, font=small)
        draw.text(((SIZE - w) / 2, top + block + 46), args.subtitle,
                  font=small, fill="#9bb0c4")

    draw.line([(SIZE / 2 - 90, SIZE - 150), (SIZE / 2 + 90, SIZE - 150)],
              fill="#5a7a99", width=4)

    img.save(args.output, "JPEG", quality=90)
    print(f"{args.output}  {os.path.getsize(args.output) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
