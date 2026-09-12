// Cloudflare doesn't offer a dashboard toggle to fully disable a Pages
// project's default `*.pages.dev` address — it's the underlying URL your
// custom domain is actually routed through, so it can't be turned off.
// This middleware runs in front of every request (page loads and /api/*
// calls alike) and 301-redirects anyone who lands on the old pages.dev URL,
// or on the bare apex domain (valostep.win with no "www"), over to the
// real domain below, so both stop being usable as separate URLs even
// though the pages.dev address itself can't be removed outright.
//
// Note: this only runs for requests that actually reach this Pages
// project. If the apex domain isn't added as a custom domain on this
// project (Cloudflare dashboard -> your Pages project -> Custom domains
// -> Set up a custom domain -> add the bare "valostep.win"), it won't
// resolve to anything at all and this redirect never gets a chance to
// run - add it there first, then this takes over automatically.
//
// If you ever change custom domains, update CUSTOM_DOMAIN and redeploy —
// like other config here, a change only takes effect on the next deploy.
const CUSTOM_DOMAIN = "https://www.valostep.win";

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);
  const target = new URL(CUSTOM_DOMAIN);
  const apexHostname = target.hostname.replace(/^www\./, "");

  if (url.hostname.endsWith(".pages.dev") || url.hostname === apexHostname) {
    url.protocol = target.protocol;
    url.hostname = target.hostname;
    url.port = target.port;
    return Response.redirect(url.toString(), 301);
  }

  return next();
}
