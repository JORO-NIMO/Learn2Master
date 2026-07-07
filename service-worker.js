/**
 * service-worker.js — Learn2Master offline cache layer.
 *
 * Caches static assets (CSS, fonts) for low-bandwidth deployment.
 * Dynamic routes (assessments, mastery data) always require a live
 * Supabase connection and are NOT cached.
 *
 * Cache version: bump CACHE_NAME to force refresh on new deployment.
 */
const CACHE_NAME = 'learn2master-v8-offline';

const STATIC_ASSETS = [
  '/static/css/variables.css',
  '/static/css/layout.css',
  '/static/css/cards.css',
  '/static/css/learning.css',
  '/static/css/subjects.css',
  '/static/css/responsive.css',
];

// Install: cache all static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: clear old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch: serve cached static assets, network-first for everything else
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only cache GET requests for static assets
  if (event.request.method === 'GET' && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // All other requests (API calls, page routes): network only
  // If offline, fail gracefully — don't serve stale dynamic content
  event.respondWith(fetch(event.request));
});
