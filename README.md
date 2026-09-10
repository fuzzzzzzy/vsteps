# vSteps

A self-hosted practice tool for identifying Valorant agents by their footstep
audio. This version is a plain static site — no backend, no size limit
beyond what your host allows, and it can be shared publicly on your own
domain.

## What's in this folder

```
index.html          the whole app (HTML + CSS + JS, single file)
clips.json           the manifest: which audio file belongs to which agent/surface
clips/                the actual audio files
build_manifest.py     regenerates clips.json by scanning clips/
auto_split.py          auto-detects and cuts clips from a recording via silence gaps
trim_clips.py          cuts a longer recording into individual clips using exact timestamps
```

There's no server, database, or upload form — you manage the clip library by
editing files in this folder and pushing to git. Cloudflare Pages rebuilds
and redeploys automatically on every push.

## One-time setup

### 1. Create a GitHub repo

1. Create a new repository on GitHub (public or private, your choice — it
   doesn't need to be public for the *site* to be public).
2. Push this folder to it:
   ```bash
   cd vsteps-static
   git init
   git add .
   git commit -m "vSteps"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

   If that push is rejected with `! [rejected] main -> main (fetch
   first)`, GitHub already has a commit on the repo — usually because
   "Add a README" (or `.gitignore`/license) got checked when the repo
   was created, even by accident. Check `https://github.com/<you>/<repo>`
   in a browser to see what's there. If it's nothing you need, overwrite
   it:
   ```bash
   git push -u origin main --force
   ```
   If there's something you actually want to keep, merge instead:
   ```bash
   git pull origin main --allow-unrelated-histories --no-edit
   git push -u origin main
   ```
   (resolve any conflict markers in the affected file first, `git add`
   it, then `git commit --no-edit` before the push).

### 2. Connect it to Cloudflare Pages

1. In the Cloudflare dashboard, go to **Workers & Pages → Create → Pages →
   Connect to Git**, and authorize/select your GitHub repo.
2. Build settings:
   - **Framework preset:** None
   - **Build command:** leave empty. If the field won't accept empty,
     type `exit 0` as a no-op.
   - **Build output directory:** `.` (a single period, meaning "repo
     root" — that's where `index.html` lives). Do **not** enter `/` —
     Cloudflare treats that as a literal subfolder named `/`, which
     doesn't exist, and the deploy fails with `[ERROR] Could not detect
     a directory containing static files`.
3. Click **Save and Deploy**. Cloudflare gives you a working
   `*.pages.dev` URL within a minute or two — the site is now live and
   public at that address.

   If a deploy ever fails with that "could not detect a directory"
   error, it means this setting got reset or mistyped — recheck it
   under **Settings → Builds & deployments** and redeploy.

### 3. Point your domain at it

1. In the Pages project, go to **Custom domains → Set up a custom domain**
   and enter your domain (or a subdomain, e.g. `vsteps.yourdomain.com`).
2. If the domain's DNS is already on Cloudflare (i.e. you bought it through
   Cloudflare Registrar, or transferred DNS there), Cloudflare adds the
   right record automatically.
3. If the domain is registered elsewhere and its DNS is *not* on
   Cloudflare, add a CNAME record at your registrar/DNS provider pointing
   your domain (or subdomain) at the `*.pages.dev` address Cloudflare
   gives you, then finish the verification step in the dashboard.
4. HTTPS is provisioned automatically — no separate certificate setup.

That's it — from here, every `git push` to `main` redeploys the live site
within roughly a minute, with no dashboard steps.

## Building your clip library

There's no bundled set of Valorant footstep clips in this repo, and that's
deliberate: the footstep audio is Riot's copyrighted asset, and Riot's fan
content policy doesn't clearly cover redistributing extracted game audio,
especially on a site that also takes donations (see [Legal Jibber
Jabber](https://www.riotgames.com/en/legal) if you want to read the actual
terms). The safe, standard way fan footstep-trainers handle this is to
record their own clips rather than distribute Riot's files — you already
own the right to record and use footage of your own gameplay.

### Fast path: `auto_split.py` (recommended for tagging a lot of clips quickly)

The fastest way to build a big library: in the Practice Range, record **one
agent on one surface per file**, walking a few steps, pausing briefly,
walking a few more, pausing, and so on, for 30-60+ seconds. Name the
recording like `jett_metal.mp4` (agent, then surface). Repeat per
agent/surface combo you want — OBS or Xbox/Windows Game Bar (`Win+G`) both
work for screen+audio capture.

Then run:
```bash
python3 auto_split.py jett_metal.mp4
```
No timestamps needed. It finds the quiet gaps between your footstep bursts
automatically (via `ffmpeg`'s silence detector) and cuts everything between
them into its own clip, already correctly named and numbered
(`jett_metal_01.mp3`, `jett_metal_02.mp3`, ...) — agent and surface are
read straight from the filename, same convention as `build_manifest.py`.
One 45-second recording with a dozen footstep bursts in it becomes a dozen
tagged clips in one command. Run it once per recording, then regenerate
the manifest (next section).

Add `--dry-run` to preview what it would cut before committing to it. If
it's splitting too aggressively (picking up keyboard/mic noise as separate
clips) or not aggressively enough (missing quiet gaps), tune `--noise` and
`--min-silence` — `python3 auto_split.py --help` explains each knob.

### Precise path: `trim_clips.py` (when you need exact control)

For clips you want to hand-place — mixing multiple agents in one
recording, or a take where the automatic split above doesn't cleanly find
the gaps — use `trim_clips.py` with timestamps you find yourself by
scrubbing through the recording in any video player:

1. Make a `cuts.csv` listing each clip you want, one per line:
   ```csv
   source,start,end,agent,surface
   practice_range_01.mp4,0:12.0,0:13.4,Jett,Metal
   practice_range_01.mp4,1:03.2,1:04.5,Jett,Wood
   practice_range_02.mp4,0:05.0,0:06.3,Sova,Sand
   ```
   (times are `M:SS.s` or `H:MM:SS.s`)
2. Run it:
   ```bash
   python3 trim_clips.py cuts.csv
   ```
   This cuts each segment straight into `clips/`, correctly named, so
   `build_manifest.py` picks them up with no further guessing. Add
   `--dry-run` first to sanity-check the plan without actually cutting
   anything.

Both scripts need `ffmpeg` installed and on your PATH — see
[ffmpeg.org/download](https://ffmpeg.org/download.html) if you don't have
it yet.

## Day-to-day: adding new clips

1. Drop new tagged audio files into `clips/` (whether cut with
   `trim_clips.py` above, or added by hand). Name them so the agent and
   surface are recognizable in the filename, separated by `_`, `-`, or
   spaces — e.g. `jett_metal_run_01.mp3` or `viper-wood-walk-03.wav`.
   Recognized surfaces: `metal`, `wood`, `sand`, `water`, `concrete`,
   `grass`.
2. Regenerate the manifest:
   ```bash
   python3 build_manifest.py
   ```
   (On Windows, this is usually just `python build_manifest.py` — Windows
   Python installs typically don't create a `python3` command. Run
   `python --version` first if you're not sure which one you have.)
   This rewrites `clips.json` from whatever's currently in `clips/`. It
   prints a count of any rows where it couldn't confidently guess the
   agent or surface — open `clips.json` and fix those by hand (it's just
   a plain JSON array, safe to hand-edit).
3. Commit and push:
   ```bash
   git add clips/ clips.json
   git commit -m "Add more footstep clips"
   git push
   ```
4. Cloudflare Pages redeploys automatically — refresh the live site in a
   minute or so and the new clips are in rotation.

To remove a clip, delete its file from `clips/`, re-run
`build_manifest.py`, and push. To fix a mistagged clip without touching
the audio file, you can just hand-edit its `agent`/`surface` fields in
`clips.json` directly and push — no need to re-run the script.

### `clips.json` format

```json
[
  { "agent": "Jett", "surface": "Metal", "filename": "jett_metal_run_01.mp3" },
  { "agent": "Sova", "surface": "Sand", "filename": "sova_sand_crouch.ogg" }
]
```

`filename` must exactly match a file in `clips/` (case-sensitive on most
hosts). `agent` should match one of the 29 current Valorant agent names for
the icon badges to render correctly — anything else still works, it just
won't get a recognizable badge.

## Local testing before you push

Opening `index.html` directly as a `file://` path won't work — browsers
block the `fetch("clips.json")` call from local files. Serve the folder
over HTTP instead:

```bash
cd vsteps-static
python3 -m http.server 8000
```
(again, `python -m http.server 8000` on most Windows installs.)

Then open `http://localhost:8000` in a browser.

## Notes

- No per-file size cap other than whatever Cloudflare Pages enforces (at
  the time of writing, Pages allows very large individual asset files —
  well beyond what a footstep clip needs).
- No admin login or upload form by design — anyone with write access to
  the git repo can add clips; anyone with the URL can practice.
- Everything client-side is in `index.html`: agent roster, icon badges,
  quiz logic, scoring, the "require surface" and "option count" settings
  (both saved per-visitor in their browser's local storage), and the
  audio-reactive waveform visualizer.
