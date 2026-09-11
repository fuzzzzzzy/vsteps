// Cloudflare Pages Function: POST /api/report
//
// Receives a clip report from any visitor's browser (see the fetch() call
// in index.html's addReport()) and forwards it to a Discord channel via a
// webhook, so reports from anyone using the live site land somewhere you
// can look at later — without the site needing a database or an admin
// login. The webhook URL itself never reaches the browser: it's read here,
// server-side, from an environment variable, so nobody viewing page source
// can grab it and spam your channel.
//
// Setup (see README.md for the full walkthrough):
//   1. In Discord: a server you control -> a channel -> Edit Channel ->
//      Integrations -> Webhooks -> New Webhook -> Copy Webhook URL.
//   2. In the Cloudflare dashboard: your Pages project -> Settings ->
//      Variables and Secrets -> Add -> name it DISCORD_WEBHOOK_URL (do this
//      for Production, and Preview too if you use preview deployments) ->
//      paste the URL -> check "Encrypt" so it's stored as a secret.
//   3. Redeploy (or just wait for the next push) so the Function picks up
//      the new environment variable.
//
// Until DISCORD_WEBHOOK_URL is set, this quietly no-ops with a 500 — the
// site still works fine, reports just don't get relayed anywhere yet.

export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.DISCORD_WEBHOOK_URL) {
    return new Response("reporting isn't configured yet", { status: 500 });
  }

  // Basic anti-abuse: a real browser sends an Origin header on a POST like
  // this one, and can't be scripted to lie about it — so if a page on some
  // other site tries to fetch() this endpoint (to spam the Discord channel,
  // say), the Origin won't match and we reject it here. This does nothing
  // against a direct scripted request (curl, a Python script) that sets its
  // own headers — there's no real defense against that without accounts or
  // CAPTCHAs, which this site intentionally doesn't have. Discord's own
  // webhook rate limit (~30 requests/minute) is the backstop for that case.
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

  const filename = String((body && body.filename) || "").slice(0, 200);
  if (!filename) {
    return new Response("missing filename", { status: 400 });
  }
  const agent = String((body && body.agent) || "").slice(0, 60);
  const surface = String((body && body.surface) || "").slice(0, 60);
  const reason = String((body && body.reason) || "").slice(0, 60);
  const auto = !!(body && body.auto);

  const reasonLabels = {
    silent: "Silent / no audio",
    wrong: "Sounds like the wrong agent",
    cut: "Cut off / clipped short",
    noisy: "Too noisy / hard to hear",
    other: "Other",
  };
  const reasonText = reasonLabels[reason] || reason || "unspecified";

  const lines = [
    "🚩 **New vSteps clip report**",
    "`" + filename + "`",
    "Agent: " + (agent || "?") + (surface && surface !== "Unknown" ? "  ·  Surface: " + surface : ""),
    "Reason: " + reasonText + (auto ? "  ·  auto-detected" : "  ·  reported by a user"),
  ];

  let discordResp;
  try {
    discordResp = await fetch(env.DISCORD_WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: lines.join("\n") }),
    });
  } catch (e) {
    return new Response("couldn't reach discord", { status: 502 });
  }

  if (!discordResp.ok) {
    return new Response("discord rejected the message", { status: 502 });
  }

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
  });
}

// Any method other than POST gets a plain 405 rather than falling through
// to some default Pages behavior.
export async function onRequestGet() {
  return new Response("method not allowed", { status: 405 });
}
