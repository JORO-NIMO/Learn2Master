/**
 * offline.js — Learn2Master service worker registration + offline sync.
 *
 * Responsibilities:
 *   1. Register service-worker.js so static assets are cached.
 *   2. Listen for the browser 'online' event and replay any pending
 *      assessment submissions from IndexedDB to the Flask /sync endpoint.
 *   3. Listen for ASSESSMENT_QUEUED messages from the service worker and
 *      show a non-intrusive banner so the learner knows their work was saved.
 */

// ── Service Worker Registration ───────────────────────────────────────────

if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/service-worker.js')
      .then(function (reg) {
        console.log('Learn2Master: service worker registered.', reg.scope);
      })
      .catch(function (err) {
        console.warn('Learn2Master: service worker not available.', err);
      });

    // Listen for messages from the service worker (e.g. ASSESSMENT_QUEUED)
    navigator.serviceWorker.addEventListener('message', function (event) {
      if (event.data && event.data.type === 'ASSESSMENT_QUEUED') {
        _showOfflineBanner(
          'You are offline. Your assessment has been saved and will be ' +
          'submitted automatically when you reconnect.'
        );
      }
    });
  });

  // If online on load, replay any previously queued items
  if (navigator.onLine) {
    window.addEventListener('load', syncOfflineQueue);
  }
}

// ── Connectivity listener ─────────────────────────────────────────────────

window.addEventListener('online', function () {
  _showOfflineBanner('Back online! Syncing your saved submissions…', 'info');
  syncOfflineQueue();
});

window.addEventListener('offline', function () {
  _showOfflineBanner(
    'You are offline. Assessments will be saved and synced when you reconnect.',
    'warning'
  );
});

// ── IndexedDB helpers ─────────────────────────────────────────────────────

/**
 * Open the 'learn2master-offline' IndexedDB database.
 * Matches the schema created by service-worker.js (version 1).
 *
 * @returns {Promise<IDBDatabase>}
 */
function openOfflineDB() {
  return new Promise(function (resolve, reject) {
    var req = indexedDB.open('learn2master-offline', 1);
    req.onupgradeneeded = function (e) {
      e.target.result.createObjectStore('offlineQueue', { autoIncrement: true });
    };
    req.onsuccess = function (e) { resolve(e.target.result); };
    req.onerror   = function ()  { reject(req.error); };
  });
}

/**
 * Read all records from an IDBObjectStore, returning [{key, value}] pairs.
 * Opens its own cursor and resolves when exhausted.
 *
 * @param {IDBObjectStore} store
 * @returns {Promise<Array<{key: IDBValidKey, value: any}>>}
 */
function getAllRecords(store) {
  return new Promise(function (resolve, reject) {
    var results = [];
    var req = store.openCursor();
    req.onsuccess = function (e) {
      var cursor = e.target.result;
      if (cursor) {
        results.push({ key: cursor.key, value: cursor.value });
        cursor.continue();
      } else {
        resolve(results);
      }
    };
    req.onerror = function () { reject(req.error); };
  });
}

// ── Sync logic ────────────────────────────────────────────────────────────

/**
 * Replay all pending IndexedDB records to POST /sync, oldest first.
 * Marks each successfully synced record as 'synced' so it is not replayed.
 * Stops on network failure and retries on the next 'online' event.
 */
async function syncOfflineQueue() {
  var db;
  try {
    db = await openOfflineDB();
  } catch (err) {
    console.warn('Learn2Master: could not open offline DB.', err);
    return;
  }

  var tx    = db.transaction('offlineQueue', 'readonly');
  var store = tx.objectStore('offlineQueue');
  var all;
  try {
    all = await getAllRecords(store);
  } catch (err) {
    db.close();
    return;
  }

  // Filter pending items and sort by key (autoIncrement — oldest first)
  var pending = all
    .filter(function (r) { return r.value && r.value.status === 'pending'; })
    .sort(function (a, b) { return a.key - b.key; });

  if (pending.length === 0) {
    db.close();
    return;
  }

  console.log('Learn2Master: syncing', pending.length, 'queued submission(s).');

  for (var i = 0; i < pending.length; i++) {
    var record = pending[i];
    var body   = Object.assign({}, record.value.payload, {
      event_type: 'assessment_submission',
      learner_id: record.value.payload.learner_id ||
                  (window.__learn2masterUserId || null)
    });

    var resp;
    try {
      resp = await fetch('/sync', {
        method:  'POST',
        body:    JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' }
      });
    } catch (netErr) {
      // Network unavailable mid-sync — stop and retry on next online event
      console.warn('Learn2Master: network unavailable during sync, will retry.', netErr);
      break;
    }

    if (resp && resp.ok) {
      // Mark as synced in IndexedDB
      try {
        var upTx    = db.transaction('offlineQueue', 'readwrite');
        var upStore = upTx.objectStore('offlineQueue');
        var updated = Object.assign({}, record.value, { status: 'synced' });
        upStore.put(updated, record.key);
        await new Promise(function (resolve) { upTx.oncomplete = resolve; });
      } catch (dbErr) {
        console.warn('Learn2Master: could not mark record synced.', dbErr);
      }
    } else {
      console.warn('Learn2Master: /sync returned non-OK for item', record.key, resp && resp.status);
    }
  }

  db.close();

  var syncedCount = pending.filter(function (r) { return r.value.status === 'synced'; }).length;
  if (syncedCount > 0 || pending.length > 0) {
    _showOfflineBanner('Offline submissions synced successfully.', 'success');
  }
}

// ── UI banner ─────────────────────────────────────────────────────────────

/**
 * Display a non-intrusive fixed banner at the top of the page.
 * Auto-dismisses after 6 seconds. Removes any existing banner first.
 *
 * @param {string} message
 * @param {'info'|'warning'|'success'} [type='info']
 */
function _showOfflineBanner(message, type) {
  type = type || 'info';

  var existing = document.getElementById('offline-sync-banner');
  if (existing) { existing.remove(); }

  var colors = {
    info:    { bg: '#1a56db', text: '#fff' },
    warning: { bg: '#ff8800', text: '#fff' },
    success: { bg: '#057a55', text: '#fff' }
  };
  var color = colors[type] || colors.info;

  var banner = document.createElement('div');
  banner.id = 'offline-sync-banner';
  banner.setAttribute('role', 'status');
  banner.setAttribute('aria-live', 'polite');
  banner.style.cssText = [
    'position:fixed',
    'top:0',
    'left:0',
    'right:0',
    'z-index:9999',
    'padding:.75rem 1.25rem',
    'text-align:center',
    'font-size:.9rem',
    'background:' + color.bg,
    'color:' + color.text,
    'box-shadow:0 2px 6px rgba(0,0,0,.25)'
  ].join(';');
  banner.textContent = message;

  document.body.prepend(banner);
  setTimeout(function () {
    if (banner.parentNode) { banner.remove(); }
  }, 6000);
}
