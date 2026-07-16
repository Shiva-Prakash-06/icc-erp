const CACHE_NAME = 'icc-erp-shell-v2';
const SHELL_ASSETS = [
  '/static/css/theme.css',
  '/static/js/app.js',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css'
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
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
});
