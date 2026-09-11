#!/usr/bin/env python3
"""
normalize_clips.py — even out the volume across every clip in clips/, so
clips recorded at different in-game volume settings don't sound wildly
louder/quieter than each other.

Why not a fixed formula: each recording session's actual loudness depends on
your in-game volume slider at the time, your recording device, distance from
the mic, etc. — there's no way to know the right correction ahead of time.
This script measures each clip's actual loudness with ffmpeg, then applies
just enough gain to bring it to a common target level.

How it works, per clip:
  1. Measure mean_volume and max_volume (in dB) with ffmpeg's volumedetect.
  2. Compute the gain needed to bring mean_volume to --target-mean.
  3. Cap that gain so max_volume + gain never exceeds -headroom dB — this
     stops a clip with one sharp loud spike from getting boosted so hard
     the spike clips/distorts, even if the clip's average is quiet.
  4. Re-encode the clip in place with that gain applied.

This edits files in clips/ directly (in place). It's all git-tracked, so if
you don't like the result, `git checkout -- clips/` undoes it. Use --dry-run
first to see the planned gain for every file without touching anything.

Requires ffmpeg on PATH (https://ffmpeg.org/download.html).

Usage:
    python3 normalize_clips.py                 # normalize everything in clips/
    python3 normalize_clips.py --dry-run        # preview only, no changes
    python3 normalize_clips.py --target-mean -18

Options:
    --dir DIR          folder of clips to normalize (default: clips/, next to this script)
    --target-mean DB   the mean loudness every clip is pulled toward, in dB
                        (default: -20.0 — a typical comfortable level for short
                        transient sounds like footsteps; more negative = quieter)
    --headroom DB       how far below 0dB (full scale) a clip's loudest peak
                        must stay after gain is applied, to avoid clipping/
                        distortion (default: 1.0)
    --max-gain DB       don't ever boost a clip by more than this many dB —
                        protects against a near-silent/broken clip (see the
                        clip-reporting feature in index.html for those) being
                        amplified into pure noise (default: 24.0)
    --dry-run           print the measured levels and planned gain for every
                        clip without changing any files
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac", ".webm"}

MEAN_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")
MAX_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")

CODECS = {
    ".mp3": ["-codec:a", "libmp3lame", "-q:a", "3"],
    ".wav": ["-codec:a", "pcm_s16le"],
    ".ogg": ["-codec:a", "libvorbis", "-q:a", "4"],
}


def measure_levels(path):
    """Returns (mean_volume_db, max_volume_db) via ffmpeg's volumedetect."""
    cmd = ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    mean_m = MEAN_RE.search(result.stderr)
    max_m = MAX_RE.search(result.stderr)
    if not mean_m or not max_m:
        return None, None
    return float(mean_m.group(1)), float(max_m.group(1))


def apply_gain(path, gain_db, out_path):
    codec_args = CODECS.get(path.suffix.lower(), [])
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(path),
        "-af", f"volume={gain_db}dB",
    ] + codec_args + [str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(SCRIPT_DIR / "clips"), help="folder of clips to normalize (default: clips/)")
    ap.add_argument("--target-mean", type=float, default=-20.0, help="target mean loudness in dB (default: -20.0)")
    ap.add_argument("--headroom", type=float, default=1.0, help="dB of headroom to leave below 0dB peak (default: 1.0)")
    ap.add_argument("--max-gain", type=float, default=24.0, help="max dB of boost applied to any one clip (default: 24.0)")
    ap.add_argument("--dry-run", action="store_true", help="preview planned gains without changing files")
    args = ap.parse_args()

    clips_dir = Path(args.dir)
    if not clips_dir.exists():
        print(f"error: {clips_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH. Install it from https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        p for p in clips_dir.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not files:
        print(f"error: no audio files found in {clips_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"{len(files)} clip(s) found. Target mean loudness: {args.target_mean} dB "
          f"(peaks capped at {-args.headroom} dB, max boost {args.max_gain} dB)\n")

    changed, skipped, failed = 0, 0, 0

    for path in files:
        mean_db, max_db = measure_levels(path)
        if mean_db is None:
            print(f"skip  {path.name}: couldn't measure volume (silent or unreadable file — check it manually)")
            skipped += 1
            continue

        desired_gain = args.target_mean - mean_db
        # Don't let the loudest peak end up clipping, even if that means
        # falling short of the target mean for a very spiky/dynamic clip.
        max_gain_before_clip = -args.headroom - max_db
        gain = min(desired_gain, max_gain_before_clip, args.max_gain)

        resulting_mean = mean_db + gain
        resulting_max = max_db + gain
        note = ""
        if gain < desired_gain - 0.05:
            note = "  (capped to avoid clipping/over-boosting)"

        print(
            f"{'[dry-run] ' if args.dry_run else ''}{path.name}: "
            f"mean {mean_db:.1f}dB, peak {max_db:.1f}dB  ->  gain {gain:+.1f}dB  "
            f"->  mean {resulting_mean:.1f}dB, peak {resulting_max:.1f}dB{note}"
        )

        if args.dry_run:
            changed += 1
            continue

        if abs(gain) < 0.1:
            skipped += 1
            continue

        with tempfile.TemporaryDirectory() as tmp:
            tmp_out = Path(tmp) / path.name
            ok, err = apply_gain(path, gain, tmp_out)
            if not ok:
                print(f"  error normalizing {path.name}: {err.strip()}", file=sys.stderr)
                failed += 1
                continue
            shutil.move(str(tmp_out), str(path))
            changed += 1

    print(
        f"\n{changed} clip(s) {'would be ' if args.dry_run else ''}normalized, "
        f"{skipped} left as-is (already close enough, or unreadable), {failed} failed."
    )
    if changed and not args.dry_run:
        print("Files were overwritten in place. If anything sounds off, `git checkout -- clips/` reverts.")
    elif args.dry_run:
        print("Nothing was changed — run again without --dry-run to actually apply these gains.")


if __name__ == "__main__":
    main()
