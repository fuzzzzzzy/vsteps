#!/usr/bin/env python3
"""
auto_split.py — auto-detect and cut individual footstep clips out of a
single-agent, single-surface recording, using silence gaps between steps.
This is the fast way to tag a large batch: trim_clips.py needs one CSV row
(with hand-found timestamps) per clip, which doesn't scale past a handful.
This script needs zero timestamps — just record, run it, done.

The idea: record one agent walking on one surface for 30-60+ seconds, with
natural (or deliberate) little pauses between groups of footsteps. This
script finds the quiet gaps with ffmpeg's silence detector and cuts
whatever's between them into its own clip — so one recording session can
produce dozens of tagged clips in a single command.

Requires ffmpeg on PATH (https://ffmpeg.org/download.html).

Usage:
    python3 auto_split.py jett_metal.mp4
    python3 auto_split.py some_recording.mp4 --agent Jett --surface Metal

If --agent/--surface are omitted, they're guessed from the source filename
using the same convention as build_manifest.py (e.g. jett_metal.mp4 ->
Jett, Metal) — so naming your recordings sensibly means you don't have to
pass any flags at all.

Surface is optional. If it's missing (no --surface, and none guessable from
the filename), clips are tagged surface=Unknown instead of erroring — there
really is no way to determine surface automatically from ordinary footage,
since Valorant never shows what you're standing on anywhere. This is the
path for repurposing existing match VODs you didn't record specifically
for this: you already know which agent you played (nothing to guess), so
tag with --agent (or a filename starting with it) and skip --surface
entirely. Agent-only clips still work fine for the site's default practice
mode — they just won't show up if the "+Surface" setting is turned on.

Tuning (only matters if it's cutting too much or too little per clip):
    --noise DB        how quiet counts as "silence" (default -30dB;
                       lower/more negative = only counts near-total
                       silence as a gap, so try -40 in a noisy recording)
    --min-silence S   minimum gap length to count as a break between
                       clips, in seconds (default 0.25)
    --min-clip S      discard detected segments shorter than this — noise
                       blips, mic pops, etc. (default 0.12)
    --max-clip S      discard detected segments longer than this — you
                       probably weren't isolating single footstep bursts
                       here, or the whole file just didn't have gaps
                       (default 4.0)
    --pad S           extra seconds kept on each side of a detected
                       segment, so the very start/end of the sound isn't
                       clipped off (default 0.05)

Options:
    --outdir DIR    where to write clips (default: clips/, next to this script)
    --format EXT    output format: mp3 (default), wav, or ogg
    --dry-run       print detected segments without cutting anything
"""

import argparse
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

SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")
DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def title_case(s):
    return re.sub(r"\S+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), s)


def guess_agent_surface(stem):
    """Same filename convention as build_manifest.py — first non-surface
    token is the agent, any surface-matching token is the surface."""
    tokens = re.split(r"[_\-\s]+", stem)
    agent, surface = None, None
    for tok in tokens:
        cleaned = re.sub(r"[0-9]+$", "", tok)
        key = cleaned.lower()
        if key in SURFACES and surface is None:
            surface = key.capitalize()
        elif cleaned and agent is None:
            agent = title_case(cleaned)
    return agent, surface


def probe_duration(path):
    result = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True)
    m = DURATION_RE.search(result.stderr)
    if not m:
        raise RuntimeError(f"couldn't read duration of {path} — is it a valid audio/video file?")
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def detect_sound_segments(path, noise_db, min_silence):
    cmd = [
        "ffmpeg", "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = result.stderr.splitlines()

    duration = probe_duration(path)
    silences = []  # (start, end)
    pending_start = None
    for line in lines:
        m = SILENCE_START_RE.search(line)
        if m:
            pending_start = float(m.group(1))
            continue
        m = SILENCE_END_RE.search(line)
        if m and pending_start is not None:
            silences.append((pending_start, float(m.group(1))))
            pending_start = None
    if pending_start is not None:
        silences.append((pending_start, duration))

    # sound segments = the gaps between silences (i.e. everything that's NOT silence)
    segments = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start > cursor:
            segments.append((cursor, s_start))
        cursor = max(cursor, s_end)
    if cursor < duration:
        segments.append((cursor, duration))
    return segments, duration


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="source recording (any format ffmpeg can read)")
    ap.add_argument("--agent", help="agent name for every clip cut from this recording")
    ap.add_argument("--surface", help="surface name for every clip cut from this recording")
    ap.add_argument("--outdir", default=str(SCRIPT_DIR / "clips"), help="output folder (default: clips/)")
    ap.add_argument("--format", choices=CODECS.keys(), default="mp3", help="output audio format (default: mp3)")
    ap.add_argument("--noise", type=float, default=-30, help="silence threshold in dB (default: -30)")
    ap.add_argument("--min-silence", type=float, default=0.25, help="min gap length to split on, seconds (default: 0.25)")
    ap.add_argument("--min-clip", type=float, default=0.12, help="discard segments shorter than this, seconds (default: 0.12)")
    ap.add_argument("--max-clip", type=float, default=4.0, help="discard segments longer than this, seconds (default: 4.0)")
    ap.add_argument("--pad", type=float, default=0.05, help="extra seconds kept on each side of a segment (default: 0.05)")
    ap.add_argument("--dry-run", action="store_true", help="print detected segments without cutting anything")
    args = ap.parse_args()

    source = Path(args.recording)
    if not source.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH. Install it from https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    agent, surface = args.agent, args.surface
    if not agent or not surface:
        guessed_agent, guessed_surface = guess_agent_surface(source.stem)
        agent = agent or guessed_agent
        surface = surface or guessed_surface
    if not agent:
        print(
            "error: couldn't determine the agent. Pass --agent explicitly, "
            "or name the file starting with the agent's name (e.g. jett_something.mp4).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not surface:
        # Surface has no signal anywhere in Valorant's footage or metadata —
        # there's nothing to guess it from unless you deliberately isolated
        # the recording to one surface. For existing/repurposed footage,
        # tag agent only and leave surface Unknown rather than fabricate one.
        surface = "Unknown"
        print("note: no surface given or guessable from the filename — tagging these clips as surface=Unknown "
              "(fine for agent-only practice; the site's \"+Surface\" mode just won't include them).")
    elif surface.lower() not in SURFACES:
        print(f"warning: {surface!r} isn't a recognized surface ({', '.join(sorted(SURFACES))}) — using it as-is", file=sys.stderr)

    print(f"source: {source}  ->  agent={agent}  surface={surface}")
    segments, duration = detect_sound_segments(source, args.noise, args.min_silence)
    print(f"duration: {duration:.2f}s — {len(segments)} candidate segment(s) detected before filtering")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    kept, skipped_short, skipped_long = 0, 0, 0
    n = 0
    while (outdir / f"{slugify(agent)}_{slugify(surface)}_{n + 1:02d}.{args.format}").exists():
        n += 1

    for start, end in segments:
        length = end - start
        if length < args.min_clip:
            skipped_short += 1
            continue
        if length > args.max_clip:
            skipped_long += 1
            continue

        padded_start = max(0.0, start - args.pad)
        padded_end = min(duration, end + args.pad)

        n += 1
        out_name = f"{slugify(agent)}_{slugify(surface)}_{n:02d}.{args.format}"
        out_path = outdir / out_name

        if args.dry_run:
            print(f"[dry-run] {padded_start:.2f}s -> {padded_end:.2f}s ({length:.2f}s)  =>  {out_path}")
            kept += 1
            continue

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-ss", str(padded_start), "-to", str(padded_end),
            "-vn", "-ac", "1",
        ] + CODECS[args.format] + [str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"error cutting segment at {start:.2f}s: {result.stderr.strip()}", file=sys.stderr)
            continue
        print(f"wrote {out_path}  ({length:.2f}s)")
        kept += 1

    print(
        f"\n{kept} clip(s) {'would be ' if args.dry_run else ''}written, "
        f"{skipped_short} skipped as too short, {skipped_long} skipped as too long."
    )
    if skipped_short + skipped_long > 0:
        print("Tune with --min-clip / --max-clip / --min-silence / --noise if that split wrong.")
    if kept and not args.dry_run:
        print("Next: python3 build_manifest.py")


if __name__ == "__main__":
    main()
