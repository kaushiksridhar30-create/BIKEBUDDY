/* Bike Buddy core: tiny event bus, API client with offline detection + auto-reconnect, voice, GPS, modal/form helpers, tab router.
   Every other file (home, ride, nav, safety, service, garage) plugs into window.BB. */
const BB = window.BB = {S: {status: null, loc: null, settings: {lang: 'hinglish', name: 'Buddy', rider: 'Rider'}, online: true, voiceErr: ''}, ev: {}, actions: {}, tabs: {}};
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
BB.esc = esc;
BB.on = (e, f) => ((BB.ev[e] = BB.ev[e] || []).push(f));
BB.once = (e, f) => { const g = d => { BB.ev[e] = BB.ev[e].filter(x => x !== g); f(d) }; BB.on(e, g) };
BB.emit = (e, d) => (BB.ev[e] || []).forEach(f => { try { f(d) } catch (x) { console.error(e, x) } });
BB.f = {km: n => n == null ? '--' : (+n).toFixed(n < 10 ? 1 : 0), dur: s => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h}h ${m}m` : `${m}m ${String(s % 60).padStart(2, '0')}s` },
  date: t => new Date(t * 1000).toLocaleDateString([], {day: 'numeric', month: 'short'}), time: t => new Date(t * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}),
  rs: n => '₹' + Math.round(n || 0).toLocaleString('en-IN')};
const BADGE = {sensor: 'sensor', gps: 'gps', user: 'user', estimate: 'estimate', sim: 'simulated', none: 'n/a'};
BB.badge = s => `<span class="bd ${esc(s || 'none')}" title="${esc({sensor: 'Real reading from a bike sensor', gps: 'Measured by phone GPS', user: 'Typed in by you', estimate: 'Calculated from other data, not measured', sim: 'Demo value, NOT from a real bike', none: 'Not available'}[s || 'none'])}">${BADGE[s || 'none'] || esc(s)}</span>`;

/* ---------- API client: detects a dead server, retries politely, reconnects automatically ---------- */
BB.api = async (method, url, body) => {
  let r; try { r = await fetch(url, {method, headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined}) }
  catch (e) { BB.setOnline(false); throw new Error('offline') }
  BB.setOnline(true); const j = await r.json().catch(() => ({error: 'bad response from server'}));
  if (!r.ok || j.error) throw Object.assign(new Error(j.error || 'HTTP ' + r.status), {status: r.status, data: j}); return j;
};
BB.get = u => BB.api('GET', u); BB.post = (u, b) => BB.api('POST', u, b || {}); BB.put = (u, b) => BB.api('PUT', u, b); BB.del = u => BB.api('DELETE', u);
BB.setOnline = on => { if (BB.S.online === on) return; BB.S.online = on; BB.renderConn(); if (on) { BB.toast('Back online', 'info'); BB.flushQueue(); BB.emit('online') } else BB.toast('Connection to the Bike Buddy server lost. Retrying automatically...', 'warn') };

BB.toast = (m, lv = 'info', ms = 4500) => { const d = document.createElement('div'); d.className = 'toast ' + lv; d.textContent = m; $('toasts').append(d); setTimeout(() => d.remove(), ms); if (lv === 'critical' && navigator.vibrate) navigator.vibrate([200, 100, 200]) };
BB.err = e => { if (e.message !== 'offline') BB.toast(e.message, 'err') };

/* ---------- connection pill ---------- */
BB.renderConn = () => {
  const c = BB.S.status && BB.S.status.conn, el = $('conn'); let k, t, tip;
  if (!BB.S.online) { k = 'offline'; t = 'SERVER OFFLINE'; tip = 'Cannot reach the Bike Buddy server. Reconnecting automatically.' }
  else if (!c) { k = 'waiting'; t = '...'; tip = '' }
  else { k = c.status; t = {simulated: 'DEMO DATA', connected: 'BIKE CONNECTED', stale: 'BIKE SLOW', disconnected: 'BIKE LOST', waiting: 'WAITING FOR BIKE'}[k]; tip = {simulated: 'No real bike connected: all bike readings are simulated demo values.', connected: 'Receiving live sensor data.', stale: 'Sensor data is arriving late.', disconnected: 'No sensor data for over a minute.', waiting: 'Live mode is on but no bike has sent data yet.'}[k] }
  el.className = 'conn ' + k; el.querySelector('span').textContent = t; el.title = tip;
};

/* ---------- status polling (one cheap call feeds the whole UI) ---------- */
let seq = null, epoch = null, backoff = 3000;
BB.poll = async () => {
  try {
    const st = await BB.get(`/api/status?since=${seq == null ? 999999999 : seq}${epoch ? '&epoch=' + epoch : ''}`); backoff = 3000;
    const first = seq == null; epoch = st.alerts.epoch; seq = st.alerts.seq; BB.S.status = st; BB.S.settings = st.settings; BB.renderConn();
    if (!first) st.alerts.new.forEach(BB.announce); BB.emit('status', st);
  } catch (e) { backoff = Math.min(backoff * 1.5, 20000); BB.renderConn() }
  setTimeout(BB.poll, BB.S.online ? 3000 : backoff);
};
BB.announce = a => { BB.toast(a.text, a.level === 'critical' ? 'critical' : a.level === 'warn' ? 'warn' : 'info', 9000);
  if (BB.S.settings.speak_alerts !== false && !BB.S.quiet) BB.speak(a.text) };

/* ---------- voice out: Gnani Timbre audio if the server has it, otherwise the browser voice ---------- */
const LANGTAG = {hinglish: 'en-IN', english: 'en-IN', hindi: 'hi-IN', kannada: 'kn-IN'};
let chain = Promise.resolve(); BB.speaking = false;
BB.playQ = (audio, text, tag) => chain = chain.then(() => new Promise(res => {
  BB.speaking = true; const done = () => { BB.speaking = false; res() };
  const fallback = () => { if (!text || !window.speechSynthesis) return done(); const u = new SpeechSynthesisUtterance(text); u.lang = tag || LANGTAG[BB.S.settings.lang] || 'en-IN'; u.onend = u.onerror = done; speechSynthesis.speak(u) };
  if (!audio) return fallback();
  const a = new Audio('data:audio/wav;base64,' + audio); a.onended = done; a.onerror = fallback; a.play().catch(fallback);
}));
BB.say = (text, r) => { if (r && r.voice_error && r.voice_error !== BB.S.voiceErr) { BB.S.voiceErr = r.voice_error; BB.toast('Voice service problem: ' + r.voice_error + ' Using the browser voice instead.', 'warn', 8000) }
  return BB.playQ(r && r.audio, text, r && r.tts_lang) };
BB.speak = async text => { try { const r = await BB.post('/api/tts', {text}); return BB.say(text, r) } catch (e) { return BB.playQ('', text) } };
BB.status = (t, bad) => { const e = $('say'); if (e) { e.textContent = t; e.classList.toggle('err', !!bad) } };

/* ---------- mic ---------- */
BB.mic = {stream: null, no: false};
BB.ensureMic = async () => { if (BB.mic.stream || BB.mic.no) return !BB.mic.no;
  try { BB.mic.stream = await navigator.mediaDevices.getUserMedia({audio: true}); return true } catch (e) { BB.mic.no = true; BB.toast('Microphone unavailable: you can type your question instead.', 'warn'); return false } };
BB.rec = async (ms, noPrompt) => { if (!await BB.ensureMic()) return noPrompt ? null : (prompt('No microphone. Type what you want to say:') || '');
  return new Promise(r => { const c = [], m = new MediaRecorder(BB.mic.stream); m.ondataavailable = e => c.push(e.data); m.onstop = () => r(new Blob(c)); m.start(); setTimeout(() => m.stop(), ms) }) };
BB.form_ = (id, blob) => { const f = new FormData(); if (id) f.append('id', id); if (typeof blob === 'string') f.append('text', blob); else f.append('audio', blob, 'a.webm'); return f };
BB.postForm = async (u, fd) => { let r; try { r = await fetch(u, {method: 'POST', body: fd}) } catch (e) { BB.setOnline(false); throw new Error('offline') } BB.setOnline(true); const j = await r.json().catch(() => ({error: 'bad response'})); if (j.error) throw new Error(j.error); return j };

/* ---------- GPS ---------- */
BB.geo = {id: null, start() {
  if (this.id != null || !navigator.geolocation) return !!navigator.geolocation;
  this.id = navigator.geolocation.watchPosition(p => { const c = p.coords; BB.S.loc = {lat: c.latitude, lon: c.longitude, speed: c.speed == null ? null : c.speed * 3.6, acc: c.accuracy, t: p.timestamp / 1000, heading: c.heading}; BB.emit('loc', BB.S.loc); BB.pushLoc() },
    e => { BB.S.geoErr = e.message; BB.emit('geoerr', e) }, {enableHighAccuracy: true, maximumAge: 2000, timeout: 20000}); return true } };
let lastPush = 0; BB.pushLoc = () => { const s = BB.S.status, l = BB.S.loc; if (!l || !s || Date.now() - lastPush < 5000 || !(s.sharing > 0 || s.ride)) return; lastPush = Date.now(); BB.post('/api/location', {lat: l.lat, lon: l.lon, speed: l.speed}).catch(() => {}) };
BB.ctx = () => BB.S.loc ? {lat: BB.S.loc.lat, lon: BB.S.loc.lon} : {};

/* ---------- offline queue for ride GPS points: nothing is lost in a tunnel or dead zone ---------- */
BB.q = {get() { try { return JSON.parse(localStorage.getItem('bbq')) || [] } catch (e) { return [] } }, set(a) { try { localStorage.setItem('bbq', JSON.stringify(a.slice(-5000))) } catch (e) {} }};
BB.postPoints = async (pts, source) => { if (!pts.length) return; if (!BB.S.online) return BB.q.set(BB.q.get().concat([{pts, source}]));
  try { return await BB.post('/api/ride/point', {points: pts, source}) } catch (e) { if (e.message === 'offline') BB.q.set(BB.q.get().concat([{pts, source}])); else throw e } };
BB.flushQueue = async () => { const q = BB.q.get(); if (!q.length) return; BB.q.set([]); let n = 0;
  for (const b of q) { try { await BB.post('/api/ride/point', {points: b.pts, source: b.source}); n += b.pts.length } catch (e) { BB.q.set(BB.q.get().concat([b])) } }
  if (n) BB.toast(`Synced ${n} saved GPS points`, 'info') };

/* ---------- modal + form helpers ---------- */
BB.modal = (html, onOpen) => { $('sheet').innerHTML = html; $('md').classList.add('on'); if (onOpen) onOpen($('sheet')) };
BB.close = () => $('md').classList.remove('on');
$('md').addEventListener('click', e => { if (e.target.id === 'md') BB.close() }); addEventListener('keydown', e => { if (e.key === 'Escape') BB.close() });
BB.form = (title, fields, submit, label = 'Save') => {
  const inp = f => f.type === 'select' ? `<select name="${f.k}">${f.opts.map(o => `<option ${o === f.val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>` :
    `<input name="${f.k}" type="${f.type || 'text'}" value="${esc(f.val == null ? '' : f.val)}" placeholder="${esc(f.ph || '')}" ${f.step ? 'step=' + f.step : ''} ${f.req ? 'required' : ''} inputmode="${f.type === 'number' ? 'decimal' : 'text'}">`;
  BB.modal(`<h2>${esc(title)}</h2><form id=bbf>${fields.map(f => `<label class=f>${esc(f.label)}${f.req ? ' *' : ''}</label>${inp(f)}`).join('')}<p class=note id=bbfe style="color:var(--r)"></p><div class=row><button class="btn pri grow" type=submit>${esc(label)}</button><button class=btn type=button id=bbfc>Cancel</button></div></form>`, s => {
    s.querySelector('#bbfc').onclick = BB.close;
    s.querySelector('#bbf').onsubmit = async ev => { ev.preventDefault(); const v = {}; new FormData(ev.target).forEach((x, k) => v[k] = x);
      try { await submit(v); BB.close() } catch (e) { s.querySelector('#bbfe').textContent = e.message === 'offline' ? 'No connection. Try again.' : e.message } } });
};
BB.confirm = (msg, yes) => BB.modal(`<h2>Please confirm</h2><p>${esc(msg)}</p><div class=row><button class="btn dng grow" id=cy>Yes</button><button class="btn grow" id=cn>No</button></div>`, s => { s.querySelector('#cn').onclick = BB.close; s.querySelector('#cy').onclick = () => { BB.close(); yes() } });

/* ---------- tabs ---------- */
BB.tab = t => { document.querySelectorAll('.view').forEach(v => v.classList.toggle('on', v.id === 'v-' + t)); document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('on', b.dataset.t === t));
  $('main').scrollTop = 0; BB.S.tab = t; if (location.hash !== '#' + t) history.replaceState(null, '', '#' + t); BB.emit('tab', t); (BB.tabs[t] || (() => {}))() };
document.querySelectorAll('#nav button').forEach(b => b.onclick = () => BB.tab(b.dataset.t));

/* ---------- actions the voice assistant can request ---------- */
BB.act = a => { if (!a) return; const f = BB.actions[a.type]; if (f) f(a) };
BB.actions.open = a => BB.tab(a.tab);

/* ---------- voice conversation (used by the orb and hands-free mode) ---------- */
BB.ask = async input => {   // input: Blob (audio) or string (already transcribed)
  const fd = BB.form_(null, input); const c = BB.ctx(); if (c.lat != null) { fd.append('lat', c.lat); fd.append('lon', c.lon) }
  const o = await BB.postForm('/api/ask', fd); BB.status(o.text ? `You: ${o.text}  →  ${o.reply}` : (o.reply || ''), false);
  if (!o.text) BB.status(await BB.whyDeaf(), true); else { BB.say(o.reply, o); BB.act(o.action) } return o };
BB.whyDeaf = async () => { try { const e = await BB.get('/api/lasterr'); return e.err || 'I did not catch that. Speak right after the orb glows, close to the mic.' } catch (x) { return 'I did not catch that.' } };

/* ---------- settings sheet ---------- */
const LG = {hinglish: 'Hinglish', english: 'English', hindi: 'हिन्दी', kannada: 'ಕನ್ನಡ'};
$('cfg').onclick = () => { const s = BB.S.settings; BB.modal(`<h2>Settings</h2>
 <label class=f>Buddy's name</label><input id=sn maxlength=15 value="${esc(s.name)}"><label class=f>Your name (shown to emergency contacts)</label><input id=sr maxlength=20 value="${esc(s.rider)}">
 <label class=f>Voice language</label><div class=row id=sl>${Object.entries(LG).map(([k, v]) => `<button class="chip ${s.lang === k ? 'on' : ''}" data-l=${k}>${v}</button>`).join('')}</div>
 <label class=f>Speed alert limit (km/h, 0 = off)</label><input id=ss type=number min=0 max=200 value="${s.speed_limit ?? 80}">
 <label class=f><input type=checkbox id=sa style="width:auto;min-height:0" ${s.speak_alerts !== false ? 'checked' : ''}> Buddy speaks alerts without being asked</label>
 <label class=f><input type=checkbox id=so style="width:auto;min-height:0" ${s.auto_odo !== false ? 'checked' : ''}> Add tracked GPS rides to the odometer</label>
 <div class=row style="margin-top:14px"><button class="btn pri grow" id=sv>Save</button><button class=btn id=sx>Close</button></div>`, m => {
  let lg = s.lang; m.querySelectorAll('#sl button').forEach(b => b.onclick = () => { lg = b.dataset.l; m.querySelectorAll('#sl button').forEach(x => x.classList.toggle('on', x === b)) });
  m.querySelector('#sx').onclick = BB.close;
  m.querySelector('#sv').onclick = async () => { try { BB.S.settings = await BB.post('/api/settings', {name: m.querySelector('#sn').value, rider: m.querySelector('#sr').value, lang: lg, speed_limit: m.querySelector('#ss').value, speak_alerts: m.querySelector('#sa').checked, auto_odo: m.querySelector('#so').checked}); BB.close(); BB.emit('settings'); BB.toast('Saved') } catch (e) { BB.err(e) } } }) };

BB.boot = () => {
  BB.renderConn(); BB.poll(); const h = location.hash.slice(1); BB.tab(['home', 'ride', 'map', 'safety', 'service', 'garage'].includes(h) ? h : 'home');
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) navigator.serviceWorker.register('/sw.js').catch(() => {});
  addEventListener('online', () => BB.poll());
};
