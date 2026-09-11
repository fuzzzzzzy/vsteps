// Cloudflare Pages Function: POST /api/identity
//
// Called once when a visitor submits the "Join leaderboard" form (see the
// #lbIdentityForm handler in index.html), before anything is saved locally.
// It either claims a brand-new name+passphrase (creating a 0/0 row for it)
// or confirms the passphrase matches an existing name — same check
// functions/api/score.js does on every synced answer, just run immediately
// so the visitor gets real feedback ("that name's taken") right away
// instead of silently finding out on their first synced answer.
//
// Same setup as functions/api/score.js (D1 database bound as env.DB) - see
// README.md's leaderboard section. Until that binding exists this quietly
// 500s, and index.html falls back to joining locally without server
// verification so the rest of the site still works.

const MAX_NAME_LEN = 24;
const MAX_PASSPHRASE_LEN = 64;

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.DB) {
    return new Response("leaderboard isn't configured yet", { status: 500 });
  }

  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return new Response("bad origin", { status: 403 });
  }

  let body;
  try {
    body = await request.json();
  } catch (e) {
    return new Response("bad json", { status: 400 });
  }

  const rawName = String((body && body.name) || "").trim().slice(0, MAX_NAME_LEN);
  const passphrase = String((body && body.passphrase) || "").slice(0, MAX_PASSPHRASE_LEN);

  if (!rawName) return new Response("missing name", { status: 400 });
  if (!passphrase) return new Response("missing passphrase", { status: 400 });

  const nameKey = rawName.toLowerCase();
  const passphraseHash = await sha256Hex(passphrase);
  const now = Date.now();

  const existing = await env.DB
    .prepare("SELECT passphrase_hash FROM players WHERE name_key = ?")
    .bind(nameKey)
    .first();

  if (existing) {
    if (existing.passphrase_hash !== passphraseHash) {
      return new Response(
        JSON.stringify({ error: "name_taken" }),
        { status: 409, headers: { "content-type": "application/json" } }
      );
    }
    // Correct passphrase for an existing name - nothing to change, just confirm.
  } else {
    await env.DB
      .prepare(
        "INSERT INTO players (name_key, display_name, passphrase_hash, correct, total, best_streak, created_at, updated_at) " +
        "VALUES (?, ?, ?, 0, 0, 0, ?, ?)"
      )
      .bind(nameKey, rawName, passphraseHash, now, now)
      .run();
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}

export async function onRequestGet() {
  return new Response("method not allowed", { status: 405 });
}
