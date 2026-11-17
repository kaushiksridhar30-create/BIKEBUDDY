/* Map tab: place search, nearby petrol pumps / hospitals / service centres, route planning and spoken turn-by-turn (Kannada, Hindi, English, Hinglish).
   Map tiles need internet (Leaflet + OpenStreetMap). Without them the lists and the voice directions still work. */
(() => {
const V = $('v-map'); let L = null, map = null, me = null, layer = null, markers = [], NAV = {on: false}, KINDS = {fuel: 'Petrol pump', hospital: 'Hospital', service: 'Service centre'};
V.innerHTML = `<div class=pill-warn id=mapMsg hidden></div><div class=row style="margin-bottom:8px"><input id=mq class=grow placeholder="Where to? e.g. Lalbagh, Indiranagar metro" style="flex:1"><button class="btn pri" id=mgo>Go</button></div>
 <div class=row style="margin-bottom:10px"><button class="chip" data-k=fuel>⛽ Petrol</button><button class=chip data-k=hospital>🏥 Hospital</button><button class=chip data-k=service>🔧 Service</button></div>
 <div id=nbox></div><div id=map></div><div id=mres class="panel list" hidden></div>`;
const hav = (a, b, c, d) => { const r = Math.PI / 180, x = (c - a) * r, y = (d - b) * r, h = Math.sin(x / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(y / 2) ** 2; return 12742000 * Math.asin(Math.sqrt(h)) };
const segDist = (p, a, b) => { const k = Math.cos(p[0] * Math.PI / 180), ax = (a[1] - p[1]) * k, ay = a[0] - p[0], bx = (b[1] - p[1]) * k, by = b[0] - p[0], dx = bx - ax, dy = by - ay, t = Math.max(0, Math.min(1, dx || dy ? -(ax * dx + ay * dy) / (dx * dx + dy * dy) : 0)); return Math.hypot(ax + t * dx, ay + t * dy) * 111320 };
const offRoute = (p, g) => { let m = 1e9; for (let i = 0; i < g.length - 1; i++) m = Math.min(m, segDist(p, g[i], g[i + 1])); return m };
const lg = () => BB.S.settings.lang || 'english';
const dist = (m, f) => m < 1000 ? f.m.replace('{x}', Math.max(10, Math.round(m / 10) * 10)) : f.km.replace('{x}', (m / 1000).toFixed(1));

function loadLeaflet() { if (L) return Promise.resolve(L); if (window.L) return Promise.resolve(L = window.L);
  return new Promise(res => { const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.append(css);
    const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'; s.onload = () => res(L = window.L); s.onerror = () => { $('mapMsg').hidden = false; $('mapMsg').textContent = 'Map tiles need internet and could not load. Search, nearby lists and spoken directions still work.'; $('map').style.display = 'none'; res(null) }; document.head.append(s) }) }
async function initMap() { if (map) return; await loadLeaflet(); if (!L) return; const l = BB.S.loc;
  map = L.map('map', {zoomControl: true}).setView(l ? [l.lat, l.lon] : [12.9716, 77.5946], l ? 15 : 11);   // camera only: the default view is NOT presented as the rider's position
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(map); layer = L.layerGroup().addTo(map); setTimeout(() => map.invalidateSize(), 100) }
BB.on('loc', l => { if (!map || !L) return; if (!me) { me = L.circleMarker([l.lat, l.lon], {radius: 8, color: '#fff', weight: 2, fillColor: '#00e5ff', fillOpacity: 1}).addTo(map); map.setView([l.lat, l.lon], 15) } else me.setLatLng([l.lat, l.lon]); if (NAV.on) { map.panTo([l.lat, l.lon]); tick(l) } });
const clear = () => { markers.forEach(m => m.remove()); markers = []; if (layer) layer.clearLayers() };

async function needLoc() { BB.geo.start(); if (BB.S.loc) return BB.S.loc;
  BB.toast('Getting your location...'); return new Promise((res, rej) => { const t = setTimeout(() => rej(new Error('Could not get your location. Allow location access.')), 10000); BB.once('loc', l => { clearTimeout(t); res(l) }) }) }

/* ---------- nearby ---------- */
async function nearby(kind) { try { const l = await needLoc(); await initMap(); const r = await BB.get(`/api/nearby?kind=${kind}&lat=${l.lat}&lon=${l.lon}`); clear();
    const res = $('mres'); res.hidden = false; res.innerHTML = `<h2>${KINDS[kind]}s near you</h2>${r.stale ? `<div class=pill-warn>Offline: showing a saved result from ${Math.round(r.age_s / 60)} min ago.</div>` : ''}` + (r.items.length ? r.items.map((p, i) =>
      `<div class=li><div class=grow><b>${esc(p.name || KINDS[kind] + ' (unnamed)')}</b><small>${p.dist_m < 1000 ? p.dist_m + ' m' : (p.dist_m / 1000).toFixed(1) + ' km'}${p.hours ? ' · ' + esc(p.hours) : ''}${p.addr ? ' · ' + esc(p.addr) : ''}</small></div>${p.phone ? `<a class="btn sm" href="tel:${esc(p.phone.replace(/[^\d+]/g, ''))}">Call</a>` : ''}<button class="btn sm go" data-i=${i}>Go</button></div>`).join('') : '<div class=empty>Nothing found nearby in OpenStreetMap.</div>');
    if (kind === 'hospital') res.insertAdjacentHTML('beforeend', '<p class=note>Emergency: call 108 (ambulance) or 112.</p>');
    res.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => { const p = r.items[+b.dataset.i]; route({name: p.name || KINDS[kind], lat: p.lat, lon: p.lon}) });
    if (L && map) { r.items.forEach(p => markers.push(L.circleMarker([p.lat, p.lon], {radius: 8, color: '#fff', weight: 1, fillColor: kind === 'hospital' ? '#ff3b3b' : '#ff8a00', fillOpacity: .95}).addTo(map).bindPopup(esc(p.name || KINDS[kind])))); if (r.items.length) map.fitBounds(L.latLngBounds(r.items.map(p => [p.lat, p.lon]).concat([[l.lat, l.lon]])), {padding: [30, 30], maxZoom: 16}) } } catch (e) { $('mres').hidden = false; $('mres').innerHTML = `<div class=empty>${e.message === 'offline' || e.status === 503 ? 'Cannot look up places without internet.' : esc(e.message)}</div>` } }
V.querySelectorAll('.chip[data-k]').forEach(b => b.onclick = () => nearby(b.dataset.k));

/* ---------- search + route ---------- */
async function search(q, auto) { q = (q || $('mq').value).trim(); if (q.length < 2) return; $('mq').value = q;
  try { const l = BB.S.loc, r = await BB.get(`/api/geocode?q=${encodeURIComponent(q)}${l ? `&lat=${l.lat}&lon=${l.lon}` : ''}`); const res = $('mres'); res.hidden = false;
    if (!r.length) { res.innerHTML = '<div class=empty>No place found. Try a landmark or area name.</div>'; if (auto) BB.speak('I could not find that place.'); return }
    if (auto) return route(r[0]); res.innerHTML = '<h2>Results</h2>' + r.map((p, i) => `<div class=li style=cursor:pointer data-i=${i}><div class=grow><b>${esc(p.name)}</b><small>${esc(p.type)}</small></div><button class="btn sm go">Go</button></div>`).join('');
    res.querySelectorAll('.li').forEach(e => e.onclick = () => route(r[+e.dataset.i])) } catch (e) { $('mres').hidden = false; $('mres').innerHTML = `<div class=empty>${e.message === 'offline' || e.status === 503 ? 'Cannot search without internet.' : esc(e.message)}</div>` } }
$('mgo').onclick = () => search(); $('mq').onkeydown = e => e.key === 'Enter' && search();

async function route(dest) { try { const l = await needLoc(); await initMap(); const r = await BB.post('/api/route', {from: {lat: l.lat, lon: l.lon}, to: {lat: dest.lat, lon: dest.lon, name: dest.name}});
    NAV = {on: false, route: r, k: 1, said: {}, off: 0, lastRe: 0, dest}; clear(); $('mres').hidden = true;
    if (L && map) { layer.addLayer(L.polyline(r.geometry, {color: '#00e5ff', weight: 6, opacity: .85})); markers.push(L.circleMarker([dest.lat, dest.lon], {radius: 9, color: '#fff', weight: 2, fillColor: '#ff8a00', fillOpacity: 1}).addTo(map)); map.fitBounds(L.polyline(r.geometry).getBounds(), {padding: [30, 30]}) }
    const f = r.fmt[lg()];
    $('nbox').innerHTML = `<div class=route-box><div class=row><div class=grow><b>${esc(dest.name)}</b><br><span class=note>${dist(r.distance_m, f)} · about ${Math.max(1, Math.round(r.duration_s / 60))} min (car timing)</span></div><button class="btn go" id=nst>Start</button><button class="btn sm" id=nx>✕</button></div></div>
     <div class="panel list" style="max-height:200px;overflow:auto">${r.steps.map(s => `<div class=li><div class=grow>${esc(s.text[lg()])}<small>${dist(s.dist, f)}</small></div></div>`).join('')}</div>`;
    $('nst').onclick = startNav; $('nx').onclick = stopNav; BB.speak(r.summary[lg()]) } catch (e) { BB.toast(e.message === 'offline' || e.status === 503 ? 'Cannot plan a route without internet.' : e.message, 'err'); if (e.status === 503) BB.speak('I cannot plan routes without internet.') } }

/* ---------- turn-by-turn ---------- */
function startNav() { NAV.on = true; NAV.k = Math.min(1, NAV.route.steps.length - 1); NAV.said = {}; BB.S.quiet = false; BB.speak(NAV.route.steps[0].text[lg()]); showNow(NAV.route.steps[NAV.k], 0); BB.status('Navigating to ' + NAV.dest.name) }
function showNow(s, d) { const f = NAV.route.fmt[lg()]; $('nbox').querySelector('.route-box').innerHTML = `<div class=row><div class="grow now">${d ? esc(dist(d, f)) + ' · ' : ''}${esc(s.text[lg()])}</div><button class="btn sm dng" id=nx>Stop</button></div>`; $('nx').onclick = stopNav }
function stopNav(speak = true) { if (NAV.route && NAV.on && speak !== false) BB.speak(NAV.route.fmt[lg()].stop); NAV = {on: false}; $('nbox').innerHTML = ''; clear() }
function tick(l) { const R = NAV.route, S = R.steps, f = R.fmt[lg()]; let s = S[NAV.k], d = hav(l.lat, l.lon, s.loc[0], s.loc[1]);
  if (l.acc != null && l.acc < 60) { NAV.off = offRoute([l.lat, l.lon], R.geometry) > 70 ? NAV.off + 1 : 0;
    if (NAV.off >= 3 && Date.now() - NAV.lastRe > 20000) { NAV.lastRe = Date.now(); BB.speak(f.re); const dest = NAV.dest; NAV.on = false; return route(dest).then(startNav) } }
  if (s.type === 'arrive') { if (d < 35) { BB.speak(s.text[lg()]); stopNav(false); return } } else if (d < 22) { NAV.k = Math.min(NAV.k + 1, S.length - 1); s = S[NAV.k]; d = hav(l.lat, l.lon, s.loc[0], s.loc[1]) }
  const seg = S[NAV.k - 1] ? S[NAV.k - 1].dist : 9999;
  for (const [th, min] of [[300, 450], [120, 200], [45, 0]]) if (d < th && seg >= min && !NAV.said[NAV.k + ':' + th]) { NAV.said[NAV.k + ':' + th] = 1; const t = s.text[lg()]; BB.speak(th === 45 ? t : f.in.replace('{d}', dist(th, f)) + t.charAt(0).toLowerCase() + t.slice(1)); break }
  showNow(s, d) }

BB.actions.navigate = a => { BB.tab('map'); search(a.query, true) };
BB.actions.nearby = a => { BB.tab('map'); nearby(a.kind) };
BB.actions.nav_stop = () => stopNav();
BB.tabs.map = () => { initMap(); BB.geo.start(); setTimeout(() => map && map.invalidateSize(), 150) };
BB.nav = {route, search, nearby, stop: stopNav};
})();
