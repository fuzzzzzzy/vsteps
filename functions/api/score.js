// Cloudflare Pages Function: POST /api/score
//
// Called once after every answered clip (see syncScoreToServer() in
// index.html) to keep a player's lifetime accuracy and best-ever streak in
// the D1 database, so the leaderboard (functions/api/leaderboard.js) can
// show real numbers across every visitor, not just whoever's currently
// looking at their own browser's local storage.
//
// Setup (see README.md's leaderboard section for the full walkthrough):
//   1. Create a D1 database (dashboard: Workers & Pages -> D1 SQL Database
//      -> Create Database), and run schema.sql against it once (its
//      Console tab -> paste -> Execute).
//   2. Bind it to this Pages project: your project -> Settings -> Bindings
//      -> Add -> D1 database binding -> variable name DB -> pick the
//      database you just created.
//   3. Redeploy so the Function picks up the binding.
//
// Until the DB binding exists, this quietly no-ops with a 500 - the rest of
// the site (including local stats) keeps working fine either way.
//
// Identity here is deliberately lightweight: a typed display name plus a
// simple passphrase, not a real account system (no email, no password
// reset). It exists only to stop someone else from casually posting under
// a name you're already using - see index.html's leaderboard section for
// more on what this does and doesn't protect against.

const MAX_NAME_LEN = 24;
const MAX_PASSPHRASE_LEN = 64;
const MAX_STREAK = 100000;
// Multiple-choice answers need at least this many options to count toward
// either leaderboard - fewer options makes correct guesses (and streaks)
// too easy to come by for the numbers to mean anything. "Type answer"
// mode has no option count and always counts - typing the exact name from
// scratch is already harder than any multiple-choice count. See index.html
// (submitAnswer -> syncScoreToServer) for what gets sent here.
const MIN_MC_OPTIONS = 5;

// Same filter as functions/api/identity.js, kept here too as a fallback in
// case a new name is ever created by a request that skips /api/identity
// (identity.js is the normal front door - see its comment for details).
// Keep both lists in sync if you edit one.
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
  const correct = !!(body && body.correct);
  let streak = parseInt(body && body.streak, 10);
  if (!Number.isFinite(streak) || streak < 0) streak = 0;
  streak = Math.min(streak, MAX_STREAK);
  const answerMode = String((body && body.mode) || "");
  let optionCount = parseInt(body && body.optionCount, 10);
  if (!Number.isFinite(optionCount)) optionCount = 0;

  if (!rawName) return new Response("missing name", { status: 400 });
  if (!passphrase) return new Response("missing passphrase", { status: 400 });

  if (answerMode === "mc" && optionCount < MIN_MC_OPTIONS) {
    // Doesn't count toward either leaderboard, but isn't an error either -
    // the visitor didn't do anything wrong, this round just doesn't
    // qualify. No DB read/write needed either way.
    return new Response(JSON.stringify({ ok: true, counted: false }), {
      headers: { "content-type": "application/json" },
    });
  }

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
        "UPDATE players SET display_name = ?, correct = correct + ?, total = total + 1, " +
        "best_streak = MAX(best_streak, ?), updated_at = ? WHERE name_key = ?"
      )
      .bind(rawName, correct ? 1 : 0, streak, now, nameKey)
      .run();
  } else {
    if (isNameBlocked(rawName)) {
      // Normally caught by /api/identity before this row ever gets
      // created - this only fires if something posts straight to
      // /api/score for a name that's never been claimed.
      return new Response(
        JSON.stringify({ error: "blocked_name" }),
        { status: 400, headers: { "content-type": "application/json" } }
      );
    }
    await env.DB
      .prepare(
        "INSERT INTO players (name_key, display_name, passphrase_hash, correct, total, best_streak, created_at, updated_at) " +
        "VALUES (?, ?, ?, ?, 1, ?, ?, ?)"
      )
      .bind(nameKey, rawName, passphraseHash, correct ? 1 : 0, streak, now, now)
      .run();
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}

export async function onRequestGet() {
  return new Response("method not allowed", { status: 405 });
}
