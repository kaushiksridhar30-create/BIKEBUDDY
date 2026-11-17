/* Network-first service worker: the app shell opens offline (last good copy), API calls are never cached. */
const C = 'bb-shell-v1', SHELL = ['/', '/static/css/app.css', '/static/js/core.js', '/static/js/home.js', '/static/js/ride.js', '/static/js/nav.js', '/static/js/safety.js', '/static/js/service.js', '/static/js/garage.js'];
self.addEventListener('install', e => e.waitUntil(caches.open(C).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => { const u = new URL(e.request.url); if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).then(r => { if (r.ok) caches.open(C).then(c => c.put(e.request, r.clone())); return r }).catch(() => caches.match(e.request).then(m => m || caches.match('/')))) });
