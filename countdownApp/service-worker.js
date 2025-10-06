// Basic service worker for offline shell
const CACHE = 'countdown-app-v1';
const ASSETS = [
  './',
  './index.html',
  './styles.css',
  './app.js',
  './manifest.json'
];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c=> c.addAll(ASSETS)));
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k=> k!==CACHE).map(k=> caches.delete(k))))
  );
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if(req.method !== 'GET') return;
  e.respondWith(
    caches.match(req).then(cached => cached || fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c=> c.put(req, copy));
      return res;
    }).catch(()=> caches.match('./index.html')))
  );
});

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch(_e) {}
  const title = data.title || '通知';
  const options = {
    body: data.body || 'メッセージがあります',
    data,
    icon: 'icon-192.png',
    badge: 'icon-192.png'
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for(const client of clientList){
        if('focus' in client) return client.focus();
      }
      if(clients.openWindow) return clients.openWindow('./index.html');
    })
  );
});
