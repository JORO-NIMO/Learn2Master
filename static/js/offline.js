/**
 * offline.js — Learn2Master service worker registration.
 *
 * Registers the service worker so CSS and static assets are cached for
 * low-bandwidth / offline access. Assessment submissions require a live
 * Supabase connection — the offline_sync_queue table handles queued events.
 */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js')
      .then(reg => {
        console.log('Learn2Master: service worker registered.', reg.scope);
      })
      .catch(err => {
        console.log('Learn2Master: service worker not available.', err);
      });
  });
}
