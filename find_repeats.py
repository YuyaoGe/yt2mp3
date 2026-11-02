#!/usr/bin/env python3
"""Find audio that repeats across episodes (intro/outro jingles, interludes)
and silence at the start or end, cut a sample of each for review, and later
remove the items you pick.

How repeats are found: every file gets a spectral fingerprint, one 32-bit
signature per 100 ms (Haitsma-Kalker style: signs of band-energy differences
over time, as +1/-1). Every pair of files is cross-correlated over all time
offsets with one FFT; a sharp peak means the two share a stretch of the same
audio at that offset, even if it was remixed or re-encoded. The stretch is then
measured frame by frame, and stretches are clustered, so one jingle used in 40
episodes is one item.

Analysing never changes the episodes; it writes samples, report.json and
index.html. `--apply R01,S02` then cuts the chosen items out (no re-encode,
tags kept, lyric timestamps shifted).
"""

import argparse
import collections
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
SR = 8000
HOP = 800            # 100 ms
WIN = 2048
FPS = SR / HOP       # frames per second
BANDS = np.geomspace(300, 3400, 34)


def decode(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def fingerprint(x, silent_db=-55):
    """One 32-bit spectral signature per frame, as a (frames, 32) matrix of +1/-1.
    Silent frames are all zeros so they never count as a match."""
    n = 1 + max(0, (len(x) - WIN) // HOP)
    freqs = np.fft.rfftfreq(WIN, 1 / SR)
    edges = np.searchsorted(freqs, BANDS)
    win = np.hanning(WIN).astype(np.float32)
    energy = []
    for c0 in range(0, n, 4000):           # chunked to keep memory flat
        idx = np.arange(WIN)[None, :] + HOP * np.arange(c0, min(n, c0 + 4000))[:, None]
        spec = np.abs(np.fft.rfft(x[idx] * win, axis=1)) ** 2
        energy.append(np.stack([spec[:, a:b].sum(1) for a, b in zip(edges[:-1], edges[1:])], 1))
    energy = np.vstack(energy) + 1e-10
    e = np.log(energy)
    diff = e[:, :-1] - e[:, 1:]
    out = np.where(diff[1:] - diff[:-1] > 0, 1.0, -1.0).astype(np.float32)
    loud = 10 * np.log10(energy.sum(1))[1:]
    out[loud < silent_db] = 0
    return out, loud


def agreement(A, B, d):
    """Per-frame similarity in [-1, 1] of A[t] and B[t - d] over their overlap."""
    lo, hi = max(0, d), min(len(A), len(B) + d)
    if hi <= lo:
        return lo, np.zeros(0)
    return lo, (A[lo:hi] * B[lo - d:hi - d]).sum(1) / 32.0


def matched_runs(A, B, d, min_len, thresh=0.36, smooth=20):
    """Stretches where A[t] ~ B[t - d]. Returns [(start_a, end_a)] in frames.
    Random audio scores ~0; the same audio re-encoded or remixed scores 0.5+."""
    lo, ag = agreement(A, B, d)
    if len(ag) < min_len:
        return []
    good = np.convolve(ag, np.ones(smooth) / smooth, mode="same") > thresh
    runs, start = [], None
    for i, g in enumerate(np.append(good, False)):
        if g and start is None:
            start = i
        elif not g and start is not None:
            if i - start >= min_len:
                runs.append((lo + start, lo + i))
            start = None
    return runs


def silences(path, noise_db, min_len):
    err = subprocess.run([FFMPEG, "-nostats", "-i", path, "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    s = [float(v) for v in re.findall(r"silence_start: ([\d.]+)", err)]
    e = [float(v) for v in re.findall(r"silence_end: ([\d.]+)", err)]
    return [(a, e[i] if i < len(e) else None) for i, a in enumerate(s)]


def speech_in(path, a, b):
    """Characters of embedded lyrics whose timestamp falls in [a, b)."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        fr = MP3(path, ID3=ID3).tags.getall("USLT")
    except Exception:
        return None
    if not fr:
        return None
    n, sample = 0, []
    for line in str(fr[0]).splitlines():
        m = re.match(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$", line)
        if m and a <= int(m[1]) * 60 + float(m[2]) < b:
            txt = m[3].strip()
            n += len(re.findall(r"[\u4e00-\u9fff]", txt))
            if txt:
                sample.append(txt)
    return n, " / ".join(sample)[:60]


def cut(src, a, b, dst):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{max(0, a):.2f}", "-to", f"{b:.2f}",
                    "-i", src, "-ac", "1", "-b:a", "96k", dst], check=True)


def decoded_length(path):
    """Duration by decoding every frame; header-based lengths can be wrong after a copy-concat."""
    err = subprocess.run([FFMPEG, "-i", path, "-map", "0:a", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    t = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)
    return int(t[-1][0]) * 3600 + int(t[-1][1]) * 60 + float(t[-1][2]) if t else 0.0


def relocate(ref, h, s, e):
    """Best place for fingerprint `ref` inside h[s..e] (seconds).
    Returns (start_seconds, agreement 0..1) or None if the stretch is too short."""
    seg = h[int(s * FPS):int(e * FPS)]
    L = len(ref)
    if L == 0 or len(seg) < L:
        return None
    n = 1 << int(np.ceil(np.log2(len(seg) + L)))
    c = np.fft.irfft((np.fft.rfft(seg, n=n, axis=0) * np.conj(np.fft.rfft(ref, n=n, axis=0))).sum(1), n=n)
    c = c[:len(seg) - L + 1]
    k = int(np.argmax(c))
    return s + k / FPS, float(c[k] / (np.abs(ref).sum() + 1e-9))


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def remove_spans(path, spans, backup=None):
    """Cut the given (start, end) spans out of an MP3 without re-encoding.
    Tags and cover are kept; lyric lines inside a span are dropped and later
    ones are shifted earlier by the removed time."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, USLT
    from transcribe import seconds_to_lrc

    length = MP3(path).info.length
    spans = sorted((max(0.0, s), min(length, e)) for s, e in spans if e > s)
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 0.3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    if sum(e - s for s, e in merged) < 0.5:
        return 0.0
    keep, t = [], 0.0
    for s, e in merged:
        if s - t > 0.2:
            keep.append((t, s))
        t = e
    if length - t > 0.2:
        keep.append((t, length))
    if not keep:
        print(f"  skipped {os.path.basename(path)}: nothing would be left")
        return 0.0

    if backup:
        dest = os.path.join(backup, os.path.basename(os.path.dirname(os.path.abspath(path))))
        os.makedirs(dest, exist_ok=True)
        if not os.path.exists(os.path.join(dest, os.path.basename(path))):
            shutil.copy2(path, dest)

    tags = ID3(path)
    work = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(path)))
    try:
        parts = []
        for i, (a, b) in enumerate(keep):
            part = os.path.join(work, f"p{i:03d}.mp3")
            subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", path,
                            "-map", "0:a", "-c", "copy", "-map_metadata", "-1", part], check=True)
            parts.append(part)
        listing = os.path.join(work, "list.txt")
        with open(listing, "w") as fh:
            fh.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
        out = os.path.join(work, "out.mp3")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", listing,
                        "-c", "copy", out], check=True)
        # Never replace the episode unless the result is exactly as long as intended
        want = sum(b - a for a, b in keep)
        got = decoded_length(out)
        if abs(got - want) > 1.0:
            raise RuntimeError(f"{os.path.basename(path)}: expected {want:.1f}s after cutting, "
                               f"got {got:.1f}s; left unchanged")

        frames = tags.getall("USLT")
        if frames:
            lines = []
            for line in str(frames[0]).splitlines():
                m = re.match(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$", line)
                if not m:
                    lines.append(line)
                    continue
                ts = int(m[1]) * 60 + float(m[2])
                # a line stamped just before a span starts is usually spoken inside it
                if any(s - 0.5 <= ts < e for s, e in merged):
                    continue
                shift = sum(e - s for s, e in merged if e <= ts)
                lines.append(f"{seconds_to_lrc(ts - shift)}{m[3]}")
            lang = frames[0].lang
            tags.delall("USLT")
            tags.add(USLT(encoding=3, lang=lang, desc="", text="\n".join(lines)))
        tags.save(out, v2_version=3)
        os.replace(out, path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return sum(e - s for s, e in merged)


def apply_report(review, ids, also, backup):
    report = json.load(open(os.path.join(review, "report.json")))
    chosen = [r for r in report if r["id"] in ids]
    missing = set(ids) - {r["id"] for r in chosen}
    if missing:
        sys.exit(f"Not in report: {', '.join(sorted(missing))}")
    per_file = collections.defaultdict(list)
    oversized = []
    for r in chosen:
        # The sample the user listened to is r["seconds"] long; refuse to cut
        # anything much longer than that under the same id
        limit = max(2 * r["seconds"], r["seconds"] + 10)
        for o in r["occurrences"]:
            if o["end"] - o["start"] > limit:
                oversized.append(f"{r['id']} {o['file'][:40]} {mmss(o['start'])}-{mmss(o['end'])}")
            per_file[o["path"]].append((o["start"], o["end"]))
    if oversized:
        sys.exit("Refusing to cut: these spans are far longer than the sample you heard:\n  "
                 + "\n  ".join(oversized))
    total = 0.0
    failed = []
    for path, spans in sorted(per_file.items()):
        if not os.path.exists(path):
            print(f"  missing {path}")
            continue
        try:
            gone = remove_spans(path, spans, backup)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            failed.append(str(exc))
            continue
        for d in also:
            twin = os.path.join(d, os.path.basename(path))
            if os.path.exists(twin):
                remove_spans(twin, spans, backup)
        if gone:
            print(f"  {os.path.basename(path)[:40]:42s} -{gone:.1f}s")
        total += gone
    print(f"\nremoved {total / 60:.1f} min from {len(per_file)} file(s). "
          f"Run find_repeats.py again before applying more: timings have shifted.")
    for msg in failed:
        print(f"  FAILED {msg}")
    # Kept for the record, but renamed so it cannot be applied twice
    os.replace(os.path.join(review, "report.json"), os.path.join(review, "report.applied.json"))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("source", help="folder of MP3s")
    p.add_argument("review", help="folder to write samples, report.json and index.html into")
    p.add_argument("--min-repeat", type=float, default=3, help="shortest shared stretch, seconds (default 3)")
    p.add_argument("--min-files", type=int, default=2, help="report repeats found in at least N files")
    p.add_argument("--silence-db", type=float, default=-50)
    p.add_argument("--silence-min", type=float, default=2, help="shortest head/tail silence, seconds")
    p.add_argument("--apply", metavar="IDS",
                   help="instead of analysing, cut the listed items (e.g. R01,R03,S02) from the "
                        "episodes, using review/report.json from the previous run")
    p.add_argument("--also", action="append", default=[],
                   help="with --apply: folder of same-named copies (e.g. compressed versions) to cut too")
    p.add_argument("--backup", metavar="DIR", help="with --apply: copy each file here before cutting")
    args = p.parse_args()

    if args.apply:
        apply_report(args.review, [i.strip().upper() for i in args.apply.split(",") if i.strip()],
                     args.also, args.backup)
        return

    files = sorted(glob.glob(os.path.join(args.source, "*.mp3")))
    print(f"fingerprinting {len(files)} files ...", flush=True)
    H, dur = [], []
    for f in files:
        x = decode(f)
        h, _ = fingerprint(x)
        H.append(h); dur.append(len(x) / SR)

    # Cross-correlate every pair over all offsets at once via FFT. The summed
    # spectrum of the 32 +-1 channels gives sum_t A[t+k].B[t] for every lag k.
    N = 1 << int(np.ceil(np.log2(2 * max(len(h) for h in H) + 1)))
    F = [np.fft.rfft(h, n=N, axis=0).astype(np.complex64) for h in H]
    min_len = int(args.min_repeat * FPS)
    min_peak = 32 * min_len * 0.35      # a min_repeat-long stretch at typical agreement
    print(f"correlating {len(files) * (len(files) - 1) // 2} pairs ...", flush=True)
    segs, pairs = [], []
    for fa in range(len(files)):
        for fb in range(fa + 1, len(files)):
            r = np.fft.irfft((F[fa] * np.conj(F[fb])).sum(1), n=N)
            noise = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-9
            cand = np.nonzero((r > min_peak) & (r > np.median(r) + 7 * noise))[0]
            if not len(cand):
                continue
            # local maxima, strongest first, at least 3 s apart
            cand = sorted(cand, key=lambda k: -r[k])
            peaks = []
            for k in cand:
                if all(abs(k - p) > 3 * FPS for p in peaks):
                    peaks.append(k)
                if len(peaks) >= 6:
                    break
            for k in peaks:
                d = int(k if k < N // 2 else k - N)       # A[t] ~ B[t - d]
                best = []
                for dd in (d - 1, d, d + 1):
                    runs = matched_runs(H[fa], H[fb], dd, min_len)
                    if sum(e - s for s, e in runs) > sum(e - s for s, e, _ in best):
                        best = [(s, e, dd) for s, e in runs]
                for s, e, dd in best:
                    ia = len(segs); segs.append([fa, s / FPS, e / FPS])
                    ib = len(segs); segs.append([fb, (s - dd) / FPS, (e - dd) / FPS])
                    pairs.append((ia, ib))
    del F

    # Union-find: partners, plus same-file segments that overlap
    parent = list(range(len(segs)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(a, b):
        parent[find(a)] = find(b)
    for a, b in pairs:
        union(a, b)
    by_file = collections.defaultdict(list)
    for i, (f, s, e) in enumerate(segs):
        by_file[f].append(i)
    for f, ids in by_file.items():
        ids.sort(key=lambda i: segs[i][1])
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = segs[ids[x]], segs[ids[y]]
                if b[1] > a[2]:
                    break
                ov = min(a[2], b[2]) - max(a[1], b[1])
                if ov > 0.5 * min(a[2] - a[1], b[2] - b[1]):
                    union(ids[x], ids[y])

    clusters = collections.defaultdict(list)
    for i in range(len(segs)):
        clusters[find(i)].append(i)
    items = []
    for ids in clusters.values():
        # merge per file into one span
        span = {}
        for i in ids:
            f, s, e = segs[i]
            if f in span:
                span[f] = (min(span[f][0], s), max(span[f][1], e))
            else:
                span[f] = (s, e)
        if len(span) < args.min_files:
            continue
        # A shared music bed under the speech can make two whole episodes look
        # alike, so a span may run on for minutes past the jingle. Re-find the
        # typical clip inside any span that is much longer than the rest.
        lens = sorted(e - s for s, e in span.values())
        med = lens[len(lens) // 2]
        ref_f, (ref_s, ref_e) = min(span.items(), key=lambda kv: abs((kv[1][1] - kv[1][0]) - med))
        for f, (s, e) in list(span.items()):
            if e - s <= max(1.5 * med, med + 5):
                continue
            hit = relocate(H[ref_f][int(ref_s * FPS):int(ref_e * FPS)], H[f], s, e)
            if hit is None or hit[1] < 0.3:
                del span[f]
            else:
                span[f] = (hit[0], hit[0] + (ref_e - ref_s))
        if len(span) < args.min_files:
            continue
        occ = []
        for f, (s, e) in sorted(span.items()):
            pos = "开头" if s < 15 else "结尾" if dur[f] - e < 15 else "中间"
            occ.append(dict(file=os.path.basename(files[f]), path=os.path.abspath(files[f]), start=round(s, 1),
                            end=round(e, 1), pos=pos, dur=round(dur[f], 1)))
        items.append(occ)
    items.sort(key=lambda o: -len(o))

    os.makedirs(args.review, exist_ok=True)
    for old in glob.glob(os.path.join(args.review, "*.mp3")):
        os.remove(old)
    report = []
    for k, occ in enumerate(items, 1):
        lens = sorted(o["end"] - o["start"] for o in occ)
        med = lens[len(lens) // 2]
        rep = min(occ, key=lambda o: abs((o["end"] - o["start"]) - med))
        poss = collections.Counter(o["pos"] for o in occ)
        where = "、".join(f"{p}{n}" for p, n in poss.most_common())
        sp = speech_in(rep["path"], rep["start"], rep["end"])
        name = f"R{k:02d}_重复{len(occ)}集_{where}_{int(round(med))}秒.mp3"
        cut(rep["path"], rep["start"] - 1, rep["end"] + 1, os.path.join(args.review, name))
        report.append(dict(id=f"R{k:02d}", kind="repeat", files=len(occ), where=where,
                           seconds=round(med, 1), sample=name, sample_from=rep["file"],
                           speech_chars=sp[0] if sp else None, speech=sp[1] if sp else "",
                           occurrences=occ))

    print("checking silence ...", flush=True)
    sil = []
    for f, d in zip(files, dur):
        for s, e in silences(f, args.silence_db, args.silence_min):
            e = d if e is None else e
            if s < 0.5:
                sil.append(("开头", f, 0.0, e))
            elif d - e < 0.5:
                sil.append(("结尾", f, s, d))
            elif e - s >= 10:
                sil.append(("中间", f, s, e))
    for k, (pos, f, s, e) in enumerate(sorted(sil, key=lambda x: -(x[3] - x[2])), 1):
        name = f"S{k:02d}_静音_{pos}_{int(round(e - s))}秒_{os.path.basename(f)[:20]}.mp3"
        # include 3 s of the audio next to the silence, so the boundary can be heard
        a, b = (s, min(e + 3, s + 20)) if pos == "开头" else (max(s - 3, e - 20), e) if pos == "结尾" else (s - 3, min(e + 3, s + 20))
        cut(f, a, b, os.path.join(args.review, name))
        report.append(dict(id=f"S{k:02d}", kind="silence", where=pos, seconds=round(e - s, 1), sample=name,
                           sample_from=os.path.basename(f),
                           occurrences=[dict(file=os.path.basename(f), path=os.path.abspath(f), start=round(s, 1), end=round(e, 1),
                                             pos=pos)]))

    json.dump(report, open(os.path.join(args.review, "report.json"), "w"), ensure_ascii=False, indent=1)

    rows = []
    for r in report:
        occ = r["occurrences"]
        detail = "<br>".join(f"{html.escape(o['file'][:40])} {mmss(o['start'])}–{mmss(o['end'])}"
                             for o in occ[:6]) + (f"<br>… 共 {len(occ)} 集" if len(occ) > 6 else "")
        kind = "重复音频" if r["kind"] == "repeat" else "静音"
        speech = ""
        if r.get("speech_chars"):
            speech = f"<div class='sp'>这段里转写出 {r['speech_chars']} 个字：{html.escape(r['speech'])}</div>"
        rows.append(f"<tr><td><b>{r['id']}</b></td><td>{kind}<br>{html.escape(r['where'])}<br>"
                    f"约 {r['seconds']} 秒" + (f"<br>{r['files']} 集" if r['kind'] == 'repeat' else "") +
                    f"</td><td><audio controls preload='none' src='{html.escape(r['sample'])}'></audio>{speech}"
                    f"<div class='src'>样本取自：{html.escape(r['sample_from'][:44])}</div></td>"
                    f"<td class='d'>{detail}</td></tr>")
    page = f"""<!doctype html><meta charset="utf-8"><title>待确认片段</title>
<style>body{{font-family:-apple-system,"PingFang SC",sans-serif;margin:24px;color:#222;background:#fafafa}}
table{{border-collapse:collapse;width:100%;background:#fff}}td{{border-bottom:1px solid #eee;padding:10px;vertical-align:top;font-size:14px}}
.d{{font-size:12px;color:#666}}.src{{font-size:12px;color:#999;margin-top:4px}}.sp{{font-size:12px;color:#b45309;margin-top:4px}}
audio{{width:320px}}h1{{font-size:20px}}p{{color:#555}}</style>
<h1>待确认片段（{os.path.basename(os.path.abspath(args.source))}）</h1>
<p>每段样本前后各多留了 1 秒（静音样本带上了相邻 3 秒的声音）。确定要删的编号后运行：<code>python3 find_repeats.py 源目录 本目录 --apply R01,S02</code></p>
<table>{''.join(rows)}</table>"""
    open(os.path.join(args.review, "index.html"), "w").write(page)
    print(f"{sum(r['kind'] == 'repeat' for r in report)} repeat group(s), "
          f"{sum(r['kind'] == 'silence' for r in report)} silence(s) -> {args.review}/index.html")


if __name__ == "__main__":
    main()
