// Cloudflare Pages Function: GET /api/leaderboard
//
// Public, read-only - returns the top players by lifetime accuracy, by
// best-ever streak, and by best-ever Challenge Mode score. See
// functions/api/score.js and functions/api/challenge.js for how those
// numbers get populated, and README.md's leaderboard section for the D1
// setup this depends on.
//
// The accuracy list requires a minimum number of answers (MIN_ATTEMPTS)
// so a player who's answered 1 clip correctly doesn't show up at a
// meaningless "100%" ahead of everyone with real sample size. Streak and
// Challenge Mode have no such floor - a single best-ever run is the whole
// point of both.

const MIN_ATTEMPTS_FOR_ACCURACY = 20;
const LIMIT = 10;

export async function onRequestGet(context) {
  const { env } = context;

  if (!env.DB) {
    return new Response("leaderboard isn't configured yet", { status: 500 });
  }

  const accuracyRows = await env.DB
    .prepare(
      "SELECT display_name, correct, total FROM players WHERE total >= ? " +
      "ORDER BY (CAST(correct AS REAL) / total) DESC, total DESC LIMIT ?"
    )
    .bind(MIN_ATTEMPTS_FOR_ACCURACY, LIMIT)
    .all();

  const streakRows = await env.DB
    .prepare("SELECT display_name, best_streak FROM players ORDER BY best_streak DESC LIMIT ?")
    .bind(LIMIT)
    .all();

  const challengeRows = await env.DB
    .prepare("SELECT display_name, best_challenge FROM players ORDER BY best_challenge DESC LIMIT ?")
    .bind(LIMIT)
    .all();

  const accuracy = (accuracyRows.results || []).map((r) => ({
    name: r.display_name,
    correct: r.correct,
    total: r.total,
    accuracy: r.total ? Math.round((r.correct / r.total) * 1000) / 10 : 0,
  }));
  const streak = (streakRows.results || []).map((r) => ({
    name: r.display_name,
    bestStreak: r.best_streak,
  }));
  const challenge = (challengeRows.results || []).map((r) => ({
    name: r.display_name,
    bestChallenge: r.best_challenge,
  }));

  return new Response(
    JSON.stringify({ accuracy, streak, challenge, minAttempts: MIN_ATTEMPTS_FOR_ACCURACY }),
    { headers: { "content-type": "application/json", "cache-control": "no-store" } }
  );
}

export async function onRequestPost() {
  return new Response("method not allowed", { status: 405 });
}
