#!/usr/bin/env python3
"""
batch_split.py — run auto_split.py over every recording in a folder in one
command, instead of typing it once per file.

This exists for working through a whole folder of Practice Range
recordings at once. Point it at the folder, and it runs auto_split.py on
every video/audio file in there, guessing each file's agent (and surface,
if present) from its filename — same naming convention as auto_split.py
and build_manifest.py (e.g. clove_concrete.mp4 -> Clove, Concrete). It
reuses build_manifest.py's agent roster and name-matching (including
aliases like "kayo" -> "KAY/O"), so agent detection is consistent with
what build_manifest.py will do to the clips afterward.

You can also limit it to a range of agents, in either Valorant's release
order or plain alphabetical order (--order, default: release) — handy
when you're recording/processing in batches and only want to run this on
agents you haven't done yet:

    python3 batch_split.py "C:\\path\\to\\recordings" --after Killjoy
    python3 batch_split.py "C:\\path\\to\\recordings" --after Killjoy --order alpha

--after is exclusive (Killjoy itself is not included). In release order
that's: Skye, Yoru, Astra, KAY/O, Chamber, Neon, Fade, Harbor, Gekko,
Deadlock, Iso, Clove, Vyse, Tejo, Waylay, Veto, Miks. Alphabetically
(--order alpha) it's a different set: Miks, Neon, Omen, Phoenix, Raze,
Reyna, Sage, Skye, Sova, Tejo, Veto, Viper, Vyse, Waylay, Yoru.

Agent names can also be typed as the two-letter shorthand shown on the
app's badges, e.g. --after kj instead of --after Killjoy.

Usage:
    python3 batch_split.py "C:\\path\\to\\recordings"
    python3 batch_split.py "C:\\path\\to\\recordings" --after Killjoy
    python3 batch_split.py "C:\\path\\to\\recordings" --after kj --order alpha
    python3 batch_split.py "C:\\path\\to\\recordings" --after Killjoy --before Clove
    python3 batch_split.py "C:\\path\\to\\recordings" --agents Jett,Sova,Neon
    python3 batch_split.py "C:\\path\\to\\recordings" --dry-run
    python3 batch_split.py "C:\\path\\to\\recordings" -- --noise -35 --format wav

Anything after a literal `--` is passed straight through to auto_split.py
for every file (e.g. --noise, --min-silence, --format — see
`python3 auto_split.py --help` for the full list).

Options:
    --after AGENT      only process files for agents after AGENT
                        (exclusive of AGENT itself) — see --order
    --before AGENT     only process files for agents before AGENT
                        (exclusive of AGENT itself) — see --order
    --order {release,alpha}
                        which ordering --after/--before use: Valorant's
                        release order (default) or plain alphabetical
    --agents A,B,C     only process files for these specific agents
                        (comma-separated, case-insensitive). Takes
                        priority over --after/--before if combined.
    --outdir DIR       passed through to auto_split.py — where clips are
                        written (default: clips/, same as auto_split.py)
    --dry-run          list which files would be processed and their
                        guessed agent/surface, without running ffmpeg
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import build_manifest  # reuse the same agent roster + alias-aware name guessing

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".ts", ".m4v", ".flv", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac"}
RECORDING_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

ROSTER_RELEASE = build_manifest.AGENTS
# Alphabetical order, ignoring case/punctuation (so "KAY/O" sorts as
# "Kayo" between Jett and Killjoy, same normalization build_manifest.py
# already uses everywhere else for name matching).
ROSTER_ALPHA = sorted(ROSTER_RELEASE, key=lambda a: build_manifest._norm(a))

# Two-letter shorthand matching the monogram badges shown in index.html
# (e.g. the "KJ" badge on Killjoy) — lets you type --after kj instead of
# spelling the full name out.
MONOGRAM_ALIASES = {
    "br": "Brimstone", "vp": "Viper", "om": "Omen", "cy": "Cypher", "sv": "Sova", "sg": "Sage",
    "px": "Phoenix", "jt": "Jett", "rz": "Raze", "bc": "Breach", "ry": "Reyna", "kj": "Killjoy",
    "sk": "Skye", "yr": "Yoru", "as": "Astra", "ko": "KAY/O", "ch": "Chamber", "ne": "Neon",
    "fd": "Fade", "hb": "Harbor", "gk": "Gekko", "dl": "Deadlock", "is": "Iso", "cl": "Clove",
    "vy": "Vyse", "tj": "Tejo", "wl": "Waylay", "vt": "Veto", "mk": "Miks",
}


def resolve_roster_name(raw):
    """Matches a user-typed agent name against the roster the same
    forgiving way build_manifest.py matches filenames (case/punctuation
    insensitive, so 'kayo' or 'kay/o' both find KAY/O), plus the app's
    two-letter monogram shorthand (e.g. 'kj' -> Killjoy)."""
    key = build_manifest._norm(raw)
    if key in MONOGRAM_ALIASES:
        return MONOGRAM_ALIASES[key]
    if key in build_manifest.AGENT_ALIASES:
        return build_manifest.AGENT_ALIASES[key]
    for agent in ROSTER_RELEASE:
        if build_manifest._norm(agent) == key:
            return agent
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="folder of recordings to process")
    ap.add_argument("--after", help="only process agents after this one (exclusive) — see --order")
    ap.add_argument("--before", help="only process agents before this one (exclusive) — see --order")
    ap.add_argument("--order", choices=["release", "alpha"], default="release",
                     help="ordering --after/--before use: 'release' (Valorant release order, default) "
                          "or 'alpha' (alphabetical, e.g. --after Killjoy --order alpha)")
    ap.add_argument("--agents", help="comma-separated list of specific agents to process (overrides --after/--before)")
    ap.add_argument("--outdir", help="passed through to auto_split.py (default: clips/)")
    ap.add_argument("--dry-run", action="store_true", help="preview what would run, without calling ffmpeg")
    # parse_known_args (not a REMAINDER positional) so our own flags are
    # recognized wherever they appear on the command line — a trailing
    # REMAINDER positional would swallow --after/--agents/--dry-run etc.
    # themselves as "passthrough" the moment they appear after `folder`.
    args, passthrough = ap.parse_known_args()
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        sys.exit(1)

    # Resolve the agent filter, if any.
    allowed_agents = None
    if args.agents:
        allowed_agents = set()
        for raw in args.agents.split(","):
            raw = raw.strip()
            if not raw:
                continue
            resolved = resolve_roster_name(raw)
            if not resolved:
                print(f"error: {raw!r} isn't a recognized agent name", file=sys.stderr)
                sys.exit(1)
            allowed_agents.add(resolved)
    elif args.after or args.before:
        roster = ROSTER_ALPHA if args.order == "alpha" else ROSTER_RELEASE
        after_idx = 0
        before_idx = len(roster)
        if args.after:
            resolved = resolve_roster_name(args.after)
            if not resolved:
                print(f"error: --after {args.after!r} isn't a recognized agent name", file=sys.stderr)
                sys.exit(1)
            after_idx = roster.index(resolved) + 1  # exclusive
        if args.before:
            resolved = resolve_roster_name(args.before)
            if not resolved:
                print(f"error: --before {args.before!r} isn't a recognized agent name", file=sys.stderr)
                sys.exit(1)
            before_idx = roster.index(resolved)  # exclusive
        allowed_agents = set(roster[after_idx:before_idx])
        if not allowed_agents:
            print("error: that --after/--before range doesn't include any agents", file=sys.stderr)
            sys.exit(1)
        print(f"Agent filter ({args.order} order): {', '.join(a for a in roster if a in allowed_agents)}\n")

    files = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in RECORDING_EXTENSIONS
    )
    if not files:
        print(f"error: no recordings found in {folder} (looked for {', '.join(sorted(RECORDING_EXTENSIONS))})", file=sys.stderr)
        sys.exit(1)

    planned = []
    skipped_no_agent = []
    skipped_filtered = []
    for path in files:
        agent = build_manifest.guess_agent(path.stem)
        surface = build_manifest.guess_surface(path.stem)
        if agent == "Unknown":
            skipped_no_agent.append(path)
            continue
        if allowed_agents is not None and agent not in allowed_agents:
            skipped_filtered.append((path, agent))
            continue
        planned.append((path, agent, surface))

    print(f"{len(files)} recording(s) found in {folder}")
    if skipped_filtered:
        print(f"{len(skipped_filtered)} skipped (agent not in the selected range/list): "
              + ", ".join(sorted(set(a for _, a in skipped_filtered))))
    if skipped_no_agent:
        print(f"{len(skipped_no_agent)} skipped (couldn't guess an agent from the filename): "
              + ", ".join(p.name for p in skipped_no_agent))
    if not planned:
        print("\nNothing to process.")
        return

    print(f"\n{len(planned)} file(s) to process:")
    for path, agent, surface in planned:
        print(f"  {path.name}  ->  {agent} / {surface}")

    if args.dry_run:
        print("\n[dry-run] nothing was actually run — drop --dry-run to process these for real.")
        return

    auto_split = str(SCRIPT_DIR / "auto_split.py")
    ok_count, fail_count = 0, 0
    for path, agent, surface in planned:
        cmd = [sys.executable, auto_split, str(path), "--agent", agent]
        if surface and surface != "Unknown":
            cmd += ["--surface", surface]
        if args.outdir:
            cmd += ["--outdir", args.outdir]
        cmd += passthrough

        print(f"\n=== {path.name} ({agent} / {surface}) ===")
        result = subprocess.run(cmd)
        if result.returncode == 0:
            ok_count += 1
        else:
            fail_count += 1
            print(f"  auto_split.py exited with an error on {path.name} (see above) — skipping to the next file.", file=sys.stderr)

    print(f"\n{ok_count} file(s) processed, {fail_count} failed.")
    if ok_count:
        print("Next: python3 build_manifest.py")


if __name__ == "__main__":
    main()
