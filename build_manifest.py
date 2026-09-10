#!/usr/bin/env python3
"""
build_manifest.py — (re)generate clips.json from the files in clips/

Usage:
    python3 build_manifest.py

Run this any time you add, remove, or rename files in the clips/ folder.
It scans clips/ for audio files, guesses the agent and surface from each
filename, and writes clips.json next to it (overwriting the old one).

Filename convention
--------------------
Separate words with underscores, hyphens, or spaces. Any token that
matches a surface name is treated as the surface; everything else in the
filename becomes the agent name (multi-word agent-ish tokens are just
title-cased). Trailing digits on a token (like a take number) are ignored
when matching, but are NOT stripped from the agent name (see below).

Examples (agent, surface):
    jett_metal_run_01.mp3      -> Jett, Metal
    viper-wood-walk-03.wav     -> Viper, Wood
    sova sand crouch.ogg       -> Sova, Sand
    kayo_concrete_02.wav       -> KAY/O, Concrete
    unknown_agent_grass.mp3    -> Unknown Agent, Grass   (fix manually)

If a file doesn't match a known agent alias, the guessed name is just the
first non-surface token, title-cased — check clips.json afterwards and
fix any rows that guessed wrong. The agent/surface fields in clips.json
are plain text, so you can also hand-edit the file directly instead of
(or in addition to) renaming files.
"""

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CLIPS_DIR = SCRIPT_DIR / "clips"
MANIFEST_PATH = SCRIPT_DIR / "clips.json"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac", ".webm"}

# Canonical agent roster (Sept 2026) — keep this in sync with the AGENTS
# array in index.html if Riot ships new agents.
AGENTS = [
    "Brimstone", "Viper", "Omen", "Cypher", "Sova", "Sage", "Phoenix", "Jett", "Raze", "Breach",
    "Reyna", "Killjoy", "Skye", "Yoru", "Astra", "KAY/O", "Chamber", "Neon", "Fade", "Harbor",
    "Gekko", "Deadlock", "Iso", "Clove", "Vyse", "Tejo", "Waylay", "Veto", "Miks",
]

SURFACES = ["Metal", "Wood", "Sand", "Water", "Concrete", "Grass"]


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _build_agent_aliases():
    aliases = {"kayo": "KAY/O", "kay": "KAY/O"}
    for agent in AGENTS:
        aliases[_norm(agent)] = agent
    return aliases


AGENT_ALIASES = _build_agent_aliases()
SURFACE_SET = {s.lower(): s for s in SURFACES}


def title_case(s: str) -> str:
    return re.sub(r"\S+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), s)


def guess_agent(filename_stem: str) -> str:
    tokens = re.split(r"[_\-\s]+", filename_stem)
    for token in tokens:
        cleaned = re.sub(r"[0-9]+$", "", token)
        key = cleaned.lower()
        if key in AGENT_ALIASES:
            return AGENT_ALIASES[key]
        if key in SURFACE_SET:
            continue  # skip surface tokens, either order
        if cleaned:
            return title_case(cleaned)
    return "Unknown"


def guess_surface(filename_stem: str) -> str:
    tokens = re.split(r"[_\-\s]+", filename_stem)
    for token in tokens:
        key = re.sub(r"[0-9]+$", "", token).lower()
        if key in SURFACE_SET:
            return SURFACE_SET[key]
    return "Unknown"


def main():
    if not CLIPS_DIR.exists():
        print(f"error: {CLIPS_DIR} does not exist — create it and add audio files first.", file=sys.stderr)
        sys.exit(1)

    files = sorted(
        p for p in CLIPS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not files:
        print(f"warning: no audio files found in {CLIPS_DIR} — writing an empty clips.json.", file=sys.stderr)

    entries = []
    unknown_agent_count = 0
    unknown_surface_count = 0
    for path in files:
        stem = path.stem
        agent = guess_agent(stem)
        surface = guess_surface(stem)
        if agent == "Unknown":
            unknown_agent_count += 1
        if surface == "Unknown":
            unknown_surface_count += 1
        entries.append({"agent": agent, "surface": surface, "filename": path.name})

    with open(MANIFEST_PATH, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")

    print(f"wrote {MANIFEST_PATH} with {len(entries)} clip(s)")
    if unknown_agent_count or unknown_surface_count:
        print(
            f"  {unknown_agent_count} with an unresolved agent, "
            f"{unknown_surface_count} with an unresolved surface — "
            f"open clips.json and fix those rows by hand."
        )


if __name__ == "__main__":
    main()
