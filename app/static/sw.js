// Scope is "/" because this file is served from the origin root by a Flask
// route, not from /static/. A worker served from /static/sw.js can only ever
// control /static/*, which is why the previous version never intercepted a
// single app navigation.
//
// The caching rule is deliberately narrow. Operational data is confidential and
// per-user: nothing under /api/, /erp/, /internal/ or any authenticated HTML is
// ever written to the cache. Only immutable build assets and the offline shell
// are stored, so a cache that outlives a logout cannot leak a record.
const CACHE_NAME = 'icc-erp-blueprint-v1';
const OFFLINE_URL = '/offline';
const SHELL_ASSETS = [OFFLINE_URL, '/static/js/app.js'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      // addAll is atomic: one 404 would discard the whole install.
      .then(cache => Promise.allSettled(SHELL_ASSETS.map(asset => cache.add(asset))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Content-hashed build output: a change produces a new filename, so serving
  // from cache can never serve something stale.
  if (url.pathname.startsWith('/static/ui/assets/')) {
    event.respondWith(
      caches.match(request).then(hit => hit || fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      }))
    );
    return;
  }

  // Navigations: always go to the network so a signed-out user can never be
  // shown a cached page. Fall back to the offline shell only when the network
  // is genuinely unavailable.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL).then(hit => hit || Response.error()))
    );
    return;
  }

  // Remaining same-origin /static/ files: network first, cache as a fallback.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
