const CACHE_NAME = 'icc-erp-sky-hub-v5';
const SHELL_ASSETS = [
  '/static/css/tokens.css',
  '/static/css/base.css',
  '/static/css/icons.css',
  '/static/css/layout.css',
  '/static/css/components.css',
  '/static/css/utilities.css',
  '/static/js/app.js',
  '/static/fonts/inter-400.woff2',
  '/static/fonts/inter-600.woff2',
  '/static/fonts/space-grotesk-500.woff2',
  '/static/fonts/space-grotesk-700.woff2',
  '/static/fonts/ibm-plex-mono-400.woff2',
  '/static/fonts/ibm-plex-mono-600.woff2'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // Operational snapshots are encrypted in IndexedDB by app.js; the service
  // worker never caches authentication, API, ERP, IGP, or report responses.
  if (!url.pathname.startsWith('/static/')) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
