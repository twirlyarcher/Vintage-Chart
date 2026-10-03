/* Vintage chart offline worker, version 2026-10-03-0293fb98. Opening the app with a signal fetches the latest page (waiting
   at most 3 seconds); without one, the copy kept on the phone is shown. */
const CACHE = "vintage-chart-2026-10-03-0293fb98";
const FILES = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png", "icon-maskable-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {
    e.respondWith(new Promise(resolve => {
      let done = false;
      const fallback = () => caches.match("index.html").then(r => { if (!done) { done = true; resolve(r || Response.error()); } });
      const timer = setTimeout(fallback, 3000);
      fetch(req).then(r => {
        if (r && r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put("index.html", copy)); }
        clearTimeout(timer); if (!done) { done = true; resolve(r); }
      }).catch(() => { clearTimeout(timer); fallback(); });
    }));
    return;
  }
  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
