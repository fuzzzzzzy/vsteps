// Cloudflare Pages Function: POST /api/challenge
//
// Called once, when a visitor chooses to save their Challenge Mode result
// (see index.html's Challenge modal - multiple choice, 5 options, drawing
// from every agent and surface in the library, 60 seconds). Unlike
// functions/api/score.js this isn't called after every answer - the
// whole run happens client-side and only the final tally gets sent here,
// the same way a high score gets submitted in most single-player arcade
// games.
//
// That tally is correct^2 / attempted, not the raw correct count - see
// the Challenge Mode block comment in index.html for why. This endpoint
// just trusts and stores whatever number the client computed (clamped to
// MAX_CHALLENGE_SCORE below) - it doesn't re-derive it from a raw
// correct/attempted count, since those aren't sent.
//
// Setup is the same D1 database as the rest of the leaderboard (see
// README.md's leaderboard section) - this reads/writes the same `players`
// table's best_challenge column. If you're adding Challenge Mode to a
// database that predates it, see schema.sql for the one-line ALTER TABLE
// to add that column.
//
// Identity here is the same lightweight name+passphrase system used
// everywhere else on the leaderboard (see functions/api/identity.js) - a
// visitor who hasn't joined yet can join and submit in the same request,
// same as the normal leaderboard's join flow just verifies first.

const MAX_NAME_LEN = 24;
const MAX_PASSPHRASE_LEN = 64;
// A generous ceiling on a single 60-second run. The correct^2/attempted
// formula tops out at "attempted" itself (when accuracy is 100%), and the
// client's answer-lock caps attempts to roughly one every ~0.7 seconds -
// so a real run tops out well under 100. This is only here so a buggy or
// malicious client can't write an absurd value into the database; raise
// it if Challenge Mode's time limit or answer-lock delay ever change.
const MAX_CHALLENGE_SCORE = 200;

// Same filter as functions/api/identity.js and functions/api/score.js,
// kept here too for the same reason: a fallback in case a new name is ever
// created by a request that skips /api/identity. Keep all three in sync.
const BLOCKED_SUBSTRINGS = [
  "fuck", "shit", "bitch", "cunt", "asshole", "nigger", "nigga", "faggot",
  "retard", "whore", "slut", "rape", "nazi", "hitler",
  "valostep", "riotgames", "admin", "moderator", "cloudflare",
];

function isNameBlocked(rawName) {
  const normalized = rawName
    .toLowerCase()
    .replace(/0/g, "o")
    .replace(/1/g, "i")
    .replace(/3/g, "e")
    .replace(/4/g, "a")
    .replace(/5/g, "s")
    .replace(/7/g, "t")
    .replace(/[$]/g, "s")
    .replace(/@/g, "a")
    .replace(/[^a-z]/g, "");
  return BLOCKED_SUBSTRINGS.some((word) => normalized.includes(word));
}

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
  let score = parseInt(body && body.score, 10);
  if (!Number.isFinite(score) || score < 0) score = 0;
  score = Math.min(score, MAX_CHALLENGE_SCORE);

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
    await env.DB
      .prepare(
        "UPDATE players SET display_name = ?, best_challenge = MAX(best_challenge, ?), updated_at = ? " +
        "WHERE name_key = ?"
      )
      .bind(rawName, score, now, nameKey)
      .run();
  } else {
    if (isNameBlocked(rawName)) {
      return new Response(
        JSON.stringify({ error: "blocked_name" }),
        { status: 400, headers: { "content-type": "application/json" } }
      );
    }
    await env.DB
      .prepare(
        "INSERT INTO players (name_key, display_name, passphrase_hash, correct, total, best_streak, best_challenge, created_at, updated_at) " +
        "VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)"
      )
      .bind(nameKey, rawName, passphraseHash, score, now, now)
      .run();
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}

export async function onRequestGet() {
  return new Response("method not allowed", { status: 405 });
}
