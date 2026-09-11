#!/usr/bin/env python3
"""
trim_clips.py — cut short footstep clips out of longer recordings and drop
them straight into clips/, correctly named for build_manifest.py.

This exists for the realistic way people build a library for this site:
record yourself walking each agent over each surface in Valorant's practice
range (screen/audio capture with OBS, Windows Game Bar, etc.), then cut the
individual footstep moments out of that longer recording. This script does
the cutting step in bulk instead of one-by-one in an audio editor.

Requires ffmpeg on PATH (https://ffmpeg.org/download.html).

Usage:
    python3 trim_clips.py cuts.csv

cuts.csv is a plain CSV file, one row per clip you want cut, with either
a header row or not (both are accepted) and these columns:

    source,start,end,agent,surface

    source    path to the recording this clip comes from (any format
              ffmpeg can read — mp4, mkv, wav, mp3, ...)
    start     start time within that recording, e.g. 1:12.5 or 00:01:12.500
    end       end time within that recording, same format
    agent     agent name for this clip, e.g. Jett
    surface   one of metal, wood, sand, water, concrete, grass (case-insensitive),
              or leave it blank if you don't know it — there's no way to
              determine surface from ordinary Valorant footage (nothing in
              the game exposes it), so blank rows are tagged surface=Unknown
              rather than guessed. Fine for agent-only practice mode; those
              clips just won't appear if "+Surface" is turned on.

Example cuts.csv (last row has an unknown surface — maybe from a VOD you
didn't record specifically for this):

    source,start,end,agent,surface
    practice_range_01.mp4,0:12.0,0:13.4,Jett,Metal
    practice_range_01.mp4,1:03.2,1:04.5,Jett,Wood
    practice_range_02.mp4,0:05.0,0:06.3,Sova,Sand
    ranked_vod_03.mp4,2:41.0,2:42.1,Sova,

Output files land in clips/ as <agent>_<surface>_<NN>.mp3, automatically
numbered per agent/surface combo so re-running with new rows never
overwrites clips from an earlier run. After running this, regenerate the
manifest as usual:

    python3 build_manifest.py

Options:
    --outdir DIR    where to write clips (default: clips/, next to this script)
    --format EXT    output format: mp3 (default), wav, or ogg
    --dry-run       print what would be cut without calling ffmpeg
"""

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SURFACES = {"metal", "wood", "sand", "water", "concrete", "grass"}
CODECS = {
    "mp3": ["-codec:a", "libmp3lame", "-q:a", "3"],
    "wav": ["-codec:a", "pcm_s16le"],
    "ogg": ["-codec:a", "libvorbis", "-q:a", "4"],
}

TIME_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$|^(\d+(?:\.\d+)?)$")


def parse_time(raw):
    """Accepts H:MM:SS.ms, MM:SS.ms, or plain seconds. Returns seconds (float)."""
    raw = raw.strip()
    m = TIME_RE.match(raw)
    if not m:
        raise ValueError(f"unrecognized time format: {raw!r}")
    if m.group(4) is not None:
        return float(m.group(4))
    h = int(m.group(1)) if m.group(1) else 0
    mm = int(m.group(2))
    ss = float(m.group(3))
    return h * 3600 + mm * 60 + ss


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def read_cuts(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row or all(not c.strip() for c in row):
                continue
            if i == 0 and row[0].strip().lower() == "source":
                continue  # header row
            if len(row) < 5:
                print(f"warning: skipping malformed row {i + 1}: {row}", file=sys.stderr)
                continue
            source, start, end, agent, surface = [c.strip() for c in row[:5]]
            rows.append({"source": source, "start": start, "end": end, "agent": agent, "surface": surface})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cuts_file", help="CSV file listing source,start,end,agent,surface")
    ap.add_argument("--outdir", default=str(SCRIPT_DIR / "clips"), help="output folder (default: clips/)")
    ap.add_argument("--format", choices=CODECS.keys(), default="mp3", help="output audio format (default: mp3)")
    ap.add_argument("--dry-run", action="store_true", help="print planned cuts without calling ffmpeg")
    args = ap.parse_args()

    if not args.dry_run and not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH. Install it from https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    cuts_path = Path(args.cuts_file)
    if not cuts_path.exists():
        print(f"error: {cuts_path} does not exist", file=sys.stderr)
        sys.exit(1)

    rows = read_cuts(cuts_path)
    if not rows:
        print("error: no cut rows found in " + str(cuts_path), file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    counters = {}
    done = 0
    failed = 0

    for i, row in enumerate(rows, start=1):
        source = Path(row["source"])
        agent = row["agent"]
        surface_key = row["surface"].strip().lower()
        if not surface_key:
            # No signal to guess surface from in ordinary footage — leave it
            # Unknown rather than fabricate one. Still fine for agent-only
            # practice mode.
            surface = "Unknown"
        elif surface_key not in SURFACES:
            print(f"warning: row {i}: {row['surface']!r} isn't a recognized surface "
                  f"({', '.join(sorted(SURFACES))}) — using it as-is anyway", file=sys.stderr)
            surface = row["surface"].strip()
        else:
            surface = surface_key.capitalize()

        try:
            start_s = parse_time(row["start"])
            end_s = parse_time(row["end"])
        except ValueError as e:
            print(f"error: row {i}: {e} — skipping", file=sys.stderr)
            failed += 1
            continue
        if end_s <= start_s:
            print(f"error: row {i}: end ({row['end']}) is not after start ({row['start']}) — skipping", file=sys.stderr)
            failed += 1
            continue

        if not args.dry_run and not source.exists():
            print(f"error: row {i}: source file not found: {source} — skipping", file=sys.stderr)
            failed += 1
            continue

        key = (slugify(agent), slugify(surface))
        counters[key] = counters.get(key, 0) + 1
        n = counters[key]
        # keep numbering unique against files already on disk from earlier runs
        while (outdir / f"{slugify(agent)}_{slugify(surface)}_{n:02d}.{args.format}").exists():
            n += 1
            counters[key] = n
        out_name = f"{slugify(agent)}_{slugify(surface)}_{n:02d}.{args.format}"
        out_path = outdir / out_name

        if args.dry_run:
            print(f"[dry-run] {source} [{row['start']} -> {row['end']}] => {out_path}")
            done += 1
            continue

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-ss", str(start_s), "-to", str(end_s),
            "-vn", "-ac", "1",
        ] + CODECS[args.format] + [str(out_path)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"error: row {i}: ffmpeg failed on {source}:\n{result.stderr.strip()}", file=sys.stderr)
            failed += 1
            continue

        print(f"wrote {out_path}  ({agent} / {surface}, {end_s - start_s:.2f}s)")
        done += 1

    print(f"\n{done} clip(s) written, {failed} failed." + (" (dry run — nothing was actually cut)" if args.dry_run else ""))
    if done and not args.dry_run:
        print("Next: python3 build_manifest.py")


if __name__ == "__main__":
    main()
