// Cloudflare doesn't offer a dashboard toggle to fully disable a Pages
// project's default `*.pages.dev` address — it's the underlying URL your
// custom domain is actually routed through, so it can't be turned off.
// This middleware runs in front of every request (page loads and /api/*
// calls alike) and 301-redirects anyone who lands on the old pages.dev URL
// over to the real domain below, so the old link stops being usable in
// practice even though the address itself can't be removed.
//
// If you ever change custom domains, update CUSTOM_DOMAIN and redeploy —
// like other config here, a change only takes effect on the next deploy.
const CUSTOM_DOMAIN = "https://www.valostep.win";

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  if (url.hostname.endsWith(".pages.dev")) {
    const target = new URL(CUSTOM_DOMAIN);
    url.protocol = target.protocol;
    url.hostname = target.hostname;
    url.port = target.port;
    return Response.redirect(url.toString(), 301);
  }

  return next();
}
