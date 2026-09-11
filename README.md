# ValoStep

A self-hosted practice tool for identifying Valorant agents by their footstep
audio. This version is a plain static site — no backend, no size limit
beyond what your host allows, and it can be shared publicly on your own
domain.

## What's in this folder

```
index.html             the whole app (HTML + CSS + JS, single file)
clips.json              the manifest: which audio file belongs to which agent/surface
clips/                   the actual audio files
icons/                   optional real per-agent icon files (falls back to a drawn monogram);
                          also holds the site logo (logo_icon.webp) and the
                          generated favicon.png built from it (see below)
og-image.png             link-preview image for shares (Discord/Twitter/etc.)
build_manifest.py        regenerates clips.json by scanning clips/
auto_split.py             auto-detects and cuts clips from a recording via silence gaps
batch_split.py            runs auto_split.py over every recording in a folder at once
trim_clips.py             cuts a longer recording into individual clips using exact timestamps
normalize_clips.py        evens out clip volume across the whole library
functions/api/report.js   optional: relays clip reports to a Discord channel (see below)
functions/api/identity.js  optional: leaderboard - claims/verifies name+passphrase on join (see below)
functions/api/score.js    optional: leaderboard - records a synced answer (see below)
functions/api/leaderboard.js  optional: leaderboard - serves the top players (see below)
schema.sql                the leaderboard's database table, for one-time setup (see below)
```

The core app needs no server, database, or upload form — you manage the
clip library by editing files in this folder and pushing to git, and
Cloudflare Pages rebuilds and redeploys automatically on every push. The
`functions/` folder adds two small, entirely optional pieces of backend —
relaying reports to Discord, and a cross-visitor leaderboard — each with
its own setup section further down; skip both and everything else still
works exactly the same.

## One-time setup

### 1. Create a GitHub repo

1. Create a new repository on GitHub (public or private, your choice — it
   doesn't need to be public for the *site* to be public).
2. Push this folder to it:
   ```bash
   cd vsteps-static
   git init
   git add .
   git commit -m "ValoStep"
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

1. In the Cloudflare dashboard, go to **Workers & Pages → Create
   application → Pages → Connect to Git**, and authorize/select your
   GitHub repo.

   Cloudflare's dashboard has been steering the main "Create" flow toward
   its newer **Workers** product instead, so depending on when you're
   reading this, "Pages" may not be an obvious option on that first
   screen — look for a smaller **"Looking to deploy Pages? Get started"**
   link (often near the bottom) and use that instead. This matters:
   Workers and Pages are different products, and only Pages
   auto-deploys anything placed in a `functions/` folder (used by the
   Discord report-relay setup further down) with zero extra
   configuration. **After deploying, check the URL Cloudflare gives you:
   it should end in `.pages.dev`. If it ends in `.workers.dev` instead,
   you ended up on a plain Worker, not Pages** — `functions/` won't be
   picked up there, and `/api/report` will 404 no matter what you do in
   Settings. Delete that project and redo this step, making sure to land
   on the Pages flow specifically.
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

### Even faster: tagging existing footage by agent only

If you already have recordings — old match VODs, clips you'd saved for
other reasons — you can reuse them without labeling anything extra,
*for the agent tag*. If it's footage of your own matches, you already know
which agent you played; that's not a guess, it's just a fact you already
have. Run `auto_split.py` with `--agent` and skip `--surface` entirely:
```bash
python3 auto_split.py ranked_vod_03.mp4 --agent Sova
```
Surface tagging can't be done this way, and there's no way around that:
Valorant never shows what material you're standing on anywhere in its UI
or files, so there's no signal anywhere to extract it from — a script
guessing at it would just be making something up. Clips from existing
footage get tagged `surface: Unknown` automatically instead. That's not a
downside for most practice, though: the site's agent-guessing mode doesn't
care about surface at all (the "+Surface" setting is off by default), so
an agent-only clip is just as useful there — it only becomes a gap if you
specifically want the combined agent+surface quiz mode, and even then you
can mix in a separately-recorded, surface-tagged batch alongside it later
without redoing anything.

One recording still needs to be one agent throughout (there's no way to
auto-detect an agent swap mid-file), but that's usually already how VODs
are organized — one file per match, one agent per match.

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
   (times are `M:SS.s` or `H:MM:SS.s`; leave `surface` blank for a clip
   from existing footage where you don't actually know the surface — it's
   tagged `Unknown` rather than guessed, same reasoning as above)
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

## Getting clip reports from any visitor (optional)

The site has a 🚩 Report button (and auto-detects silent/broken clips) —
see `functions/api/report.js`. By default those reports only save to
*that visitor's own browser* (local storage), so you'd never see reports
from anyone but yourself. To have every visitor's reports relayed to a
Discord channel you control, so you can review them later no matter who
flagged the clip:

**This only works if your site is deployed on Cloudflare Pages, not a
plain Cloudflare Worker** — check the URL your project gave you: it
should end in `.pages.dev` (or your custom domain). If it ends in
`.workers.dev`, `functions/` is never picked up and `/api/report` will
404 regardless of anything set below — see the "ended up on a plain
Worker" note in step 2 of the setup section above for how to fix that
first.

1. In a Discord server you control, go to a channel -> **Edit Channel ->
   Integrations -> Webhooks -> New Webhook**, then **Copy Webhook URL**.
   (Discord webhooks only work in server channels, not DMs — a private
   server with just you in it works fine.)
2. In the Cloudflare dashboard: your Pages project -> **Settings ->
   Variables and Secrets -> Add** -> variable name `DISCORD_WEBHOOK_URL`,
   paste the URL as its value, and check **Encrypt** so it's stored as a
   secret rather than plain text (once saved, you won't be able to view
   the value again — only replace it). Do this for the Production
   environment (and Preview too, if you use preview deployments).
3. Push/redeploy. `functions/api/report.js` — a small Cloudflare Pages
   Function that ships in this repo — picks up the new environment
   variable automatically; no other setup needed.

Until `DISCORD_WEBHOOK_URL` is set, reports still work exactly as before
(saved locally, visible in the "Reported clips" panel to whoever flagged
them) — the site just doesn't have anywhere else to relay them yet.

The webhook URL itself never touches the browser — it's only ever read
server-side inside the Function — so nobody viewing page source can grab
it and spam your channel.

### Abuse protection on `/api/report`

`functions/api/report.js` checks that the request's `Origin` header matches
the site itself, which stops a page on some *other* site from silently
spamming your Discord channel through a visitor's browser. It does **not**
stop a direct scripted request (curl, a Python script) that sets its own
headers — there's no real defense against that without adding accounts or
CAPTCHAs, which this site intentionally doesn't have. Discord's own webhook
rate limit (roughly 30 requests/minute) is the practical backstop for that
case, and is probably fine for a small hobby project.

If you want a stronger, IP-based rate limit at Cloudflare's edge: **Settings
→ Security → WAF → Rate limiting rules** (the free plan includes one rule).
Set it to match path `/api/report` and block after a handful of requests
from the same IP within 10 seconds. One catch: Cloudflare's WAF/Rate
Limiting products apply to domains (zones) *you* control — they won't do
anything on the shared `*.pages.dev` subdomain. This only works once
you've attached your own [custom domain](#3-point-your-domain-at-it) to
the project.

## Leaderboard (optional)

Tracks the top players by lifetime accuracy and by best-ever streak across
*everyone* who's played, not just the current browser. This needs a real
database — unlike the Discord report relay, there's no way around that,
since a leaderboard's whole point is state shared across visitors.

**Identity is intentionally lightweight**: a visitor picks a display name
and a passphrase (via the 🏆 Leaderboard panel), which get remembered in
their browser and resent with every synced answer. There's no email, no
password reset, no real account — it exists purely so someone else can't
casually post under a name you're already using. It does **not** stop a
determined person from opening devtools and POSTing fabricated results
under their *own* name — see the "honest caveat" this README's earlier
conversation about this feature already covers: any client-reported stat
can be spoofed by whoever controls the client. Fine for a leaderboard
among friends; not a competitive-integrity guarantee.

### Setup

1. **Create the database.** Cloudflare dashboard → **Workers & Pages → D1
   SQL Database → Create Database**. Name it anything (e.g. `vsteps-db`).
2. **Create the table.** Open the database you just made → **Console** tab
   → paste the SQL below → **Execute**. This only needs to be done once.

   ```sql
   CREATE TABLE IF NOT EXISTS players ( name_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, passphrase_hash TEXT NOT NULL, correct INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0, best_streak INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL );
   ```

   Use this single-line version, not `schema.sql`'s — the dashboard's
   Console box flattens pasted newlines onto one line, which turns every
   `--` comment in `schema.sql` into one giant comment that swallows the
   real statement after it too, and Cloudflare rejects the result with
   "Requests without any query are not supported." `schema.sql` itself is
   still the source of truth for the table shape (and safe to run via
   `wrangler d1 execute` if you use the CLI, since that doesn't flatten
   newlines) — just don't paste it as-is into the Console box.
3. **Bind it to the Pages project.** Your `vsteps` Pages project →
   **Settings → Bindings → Add → D1 database binding** → variable name
   **`DB`** (this exact name — `functions/api/identity.js`,
   `functions/api/score.js`, and `functions/api/leaderboard.js` all read
   `env.DB`) → pick the database from step 1. Do this for Production (and
   Preview too, if you use it).
4. **Redeploy** — push a commit, or **Retry deployment** on the latest one
   — so the Function picks up the new binding. Same gotcha as the Discord
   webhook variable: a binding added after a deployment doesn't apply
   retroactively to it.

Until the `DB` binding exists, `/api/identity`, `/api/score`, and
`/api/leaderboard` quietly 500 — the rest of the site, including each
visitor's own local stats, keeps working fine either way, and "Join
leaderboard" still works locally (it just can't verify the passphrase
against anything yet).

### Notes on the design

- Accuracy is lifetime (correct ÷ total answers, all-time, per name), not
  a single session — accumulates across every device/browser using the
  same name+passphrase.
- The accuracy leaderboard requires at least 20 answered clips to qualify
  (`MIN_ATTEMPTS_FOR_ACCURACY` in `functions/api/leaderboard.js`) so a
  lucky 1-for-1 doesn't outrank someone with real sample size. Adjust that
  constant if you want a different bar.
- The passphrase is hashed (SHA-256) before it's ever written to the
  database — `functions/api/score.js` never stores or compares it in
  plain text — but it's still only as strong as whatever the visitor
  types, and it's stored in their browser's local storage in plain text
  (not the database) so it can be resent automatically. Treat this the
  same as any other low-stakes shared password, not a real credential.
- `/api/score` has the same Origin-header check as `/api/report` (see the
  report-relay section above) and the same limits — it stops another
  site's script from posting through a visitor's browser, not a direct
  scripted request. A Cloudflare Rate Limiting rule (see above, needs a
  custom domain) is the real fix if that becomes a problem.
- Clicking "Join leaderboard" calls `functions/api/identity.js`
  immediately, which claims a brand-new name or verifies the passphrase
  against an existing one — a taken name shows a real error right away
  instead of silently saving locally and only failing on the first
  synced answer. If a name somehow still gets reused between joining and
  a later sync (e.g. the D1 data was reset), `/api/score`'s 409 clears
  the local identity and the leaderboard panel explains why the next
  time it's opened, rather than just quietly dropping back to the join
  form.
- New display names are checked against a small profanity/impersonation
  filter (`BLOCKED_SUBSTRINGS` in `functions/api/identity.js`, duplicated
  in `functions/api/score.js` as a fallback — keep both in sync if you
  edit one) before they're ever saved, so they can't show up on the
  public leaderboard at all. It lowercases the name, normalizes common
  leetspeak substitutions (`0`→o, `1`→i, `3`→e, etc.), and strips
  punctuation/spaces before matching, so simple evasion like `f.u.c.k` or
  `sh1t` still gets caught. It's a short, deliberately non-exhaustive
  list — add more words as you see fit. An existing name is never
  re-checked (only brand-new ones), so this can't retroactively affect
  anyone already on the board.

## Notes

- `og-image.png` is the link-preview image shown when the site's URL is
  shared on Discord/Twitter/etc. — original artwork generated for this
  project, not Riot assets. `index.html`'s `<head>` references it (and
  `og:url`) as an absolute `https://www.valostep.win/...` URL, since
  preview crawlers fetch those directly rather than resolving them
  relative to the page — update both if you ever move to a different
  custom domain.
- `functions/_middleware.js` 301-redirects any request that comes in on
  the project's `*.pages.dev` address over to `CUSTOM_DOMAIN` at the top
  of that file. Cloudflare has no dashboard setting to disable the
  pages.dev address outright, so this is the practical equivalent —
  update `CUSTOM_DOMAIN` (and redeploy) if the custom domain ever
  changes.
- The site logo is `icons/logo_icon.webp` (a white footstep mark, meant
  to sit on a colored background) — `index.html`'s header displays it
  directly on a teal CSS badge (`.brand-logo`). `icons/favicon.png` is a
  separate, pre-composited PNG (the logo flattened onto the same teal
  badge, since a favicon can't use CSS) used by the `<link rel="icon">`
  tag. If you replace the logo, regenerate `favicon.png` to match —
  it's just the new logo centered with ~18% padding on all sides over a
  `#0E8A79`, ~22%-corner-radius rounded square, exported at 256×256.
- No per-file size cap other than whatever Cloudflare Pages enforces (at
  the time of writing, Pages allows very large individual asset files —
  well beyond what a footstep clip needs).
- No admin login or upload form by design — anyone with write access to
  the git repo can add clips; anyone with the URL can practice.
- Everything client-side is in `index.html`: agent roster, icon badges,
  quiz logic, scoring, the "require surface" and "option count" settings
  (both saved per-visitor in their browser's local storage), and the
  audio-reactive waveform visualizer.
