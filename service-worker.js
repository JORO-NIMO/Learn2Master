/**
 * service-worker.js — Learn2Master offline cache + assessment queue layer.
 *
 * Two responsibilities:
 *   1. Cache static assets (CSS) for low-bandwidth deployment.
 *   2. Intercept POST /assessment/<id>/submit when offline, queue the
 *      submission in IndexedDB, and replay it to /sync on reconnect.
 *
 * Cache version: bump CACHE_NAME to force a refresh on new deployment.
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

// ── IndexedDB helper: queue an offline assessment payload ─────────────────

/**
 * Open (or upgrade) the IndexedDB 'learn2master-offline' database and
 * append a pending payload to the 'offlineQueue' object store.
 *
 * @param {Object} payload  - Flat object of form field key/value pairs
 *                            plus _assessment_id and _queued_at metadata.
 * @returns {Promise<void>}
 */
function enqueueOffline(payload) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('learn2master-offline', 1);

    req.onupgradeneeded = function (e) {
      // Create the store on first open or version bump
      e.target.result.createObjectStore('offlineQueue', { autoIncrement: true });
    };

    req.onsuccess = function (e) {
      const db    = e.target.result;
      const tx    = db.transaction('offlineQueue', 'readwrite');
      const store = tx.objectStore('offlineQueue');
      store.add({ payload: payload, status: 'pending', queued_at: payload._queued_at });
      tx.oncomplete = function () { db.close(); resolve(); };
      tx.onerror    = function () { db.close(); reject(tx.error); };
    };

    req.onerror = function () { reject(req.error); };
  });
}

// ── Install: pre-cache all static assets ─────────────────────────────────

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// ── Activate: clear stale caches ─────────────────────────────────────────

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) { return key !== CACHE_NAME; })
            .map(function (key) { return caches.delete(key); })
      );
    })
  );
  self.clients.claim();
});

// ── Fetch: intercept offline assessment submits; cache-first for statics ──

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);

  // ── Branch 1: Intercept POST /assessment/<id>/submit ───────────────────
  var isAssessmentSubmit =
    event.request.method === 'POST' &&
    /\/assessment\/\d+\/submit/.test(url.pathname);

  if (isAssessmentSubmit) {
    event.respondWith(
      fetch(event.request.clone()).catch(function () {
        // Network failure → offline path: queue payload in IndexedDB
        return event.request.formData().then(function (formData) {
          var payload = {};
          formData.forEach(function (value, key) {
            payload[key] = value;
          });
          // Extract assessment_id from the URL path
          var match = url.pathname.match(/\/assessment\/(\d+)\/submit/);
          payload._assessment_id = match ? match[1] : null;
          payload._queued_at     = Date.now();

          return enqueueOffline(payload).then(function () {
            // Notify all open clients so the page can show a banner
            self.clients.matchAll({ includeUncontrolled: true }).then(function (clients) {
              clients.forEach(function (client) {
                client.postMessage({ type: 'ASSESSMENT_QUEUED' });
              });
            });

            // Return a synthetic 202 so the page does not hang
            return new Response(
              JSON.stringify({ queued: true }),
              {
                status: 202,
                headers: { 'Content-Type': 'application/json' }
              }
            );
          });
        });
      })
    );
    return;
  }

  // ── Branch 2: Cache-first for GET static assets ────────────────────────
  if (event.request.method === 'GET' && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        return cached || fetch(event.request).then(function (response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(event.request, clone);
          });
          return response;
        });
      }).catch(function () {
        return caches.match(event.request);
      })
    );
    return;
  }

  // ── Branch 3: Network-only for all other requests ──────────────────────
  // Dynamic routes require live data — no stale HTML served.
  event.respondWith(fetch(event.request));
});
