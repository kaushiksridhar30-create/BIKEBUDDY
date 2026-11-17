/* Safety: crash detection with a confirm-countdown (fewer false alarms), SOS with a cancel window, live-location sharing, emergency contacts,
   nearby hospitals + emergency numbers. We never claim an alert was sent unless the server says it really was. */
(() => {
const V = $('v-safety'), OV = $('ov'); let armed = false, buf = [], acc = [], cool = 0, peak = 0, armedT = 0, cur = null, busyInc = false, ride40 = false;
V.innerHTML = `<div class=panel id=cdp></div><button class=sos id=sos>SOS</button><p class=note style="text-align:center">Tap SOS: you get 5 seconds to cancel, then your contacts and a live tracking link are alerted.</p>
 <div class=panel id=shp></div><div class=panel id=ctp></div><div class=panel id=hsp></div>
 <div class=panel><h2>Emergency numbers (India)</h2><div class=tiles id=nums></div></div><div class=panel><h2>Recent alerts</h2><div id=incs class=list></div></div>
 <details class=panel><summary>Test crash detection</summary><p class=note>Safe tests: nothing is sent to real contacts unless SMS or a webhook is configured on the server.</p><div class=row><button class="btn sm" id=tcr>Simulate crash</button><button class="btn sm" id=tbk>Replay bike telemetry crash</button><label class=note><input type=checkbox id=r40 style="width:auto;min-height:0"> Pretend I'm riding at 40 km/h</label></div><p class=note>Real test: tick the box, enable detection, then drop the phone onto a cushion (never a hard floor).</p></details>`;
const contactsMsg = (c, url) => `SOS from ${BB.S.settings.rider || 'Rider'}. Live location: ${url}`;

/* ---------- crash detection (impact, then stillness; speed decides crash vs dropped phone on the server) ---------- */
function cdPanel() { $('cdp').innerHTML = `<div class=row><h2 class=grow style="margin:0">Crash detection</h2><span class="st ${armed ? 'ok' : 'soon'}">${armed ? 'ON' : 'OFF'}</span></div>
  <p class=note>Watches the phone's accelerometer for a hard impact followed by stillness. If it triggers, Buddy asks if you are OK and you get a countdown. No answer means help is alerted. Works only while this page is open and on screen.</p>
  <button class="btn ${armed ? '' : 'pri'}" id=cde style="width:100%">${armed ? 'Turn off' : 'Enable crash detection'}</button>` + (window.DeviceMotionEvent ? '' : '<p class=note style="color:var(--o)">This device reports no motion sensor.</p>');
  $('cde').onclick = async () => { if (armed) { armed = false; return cdPanel() }
    try { if (window.DeviceMotionEvent && DeviceMotionEvent.requestPermission) { if (await DeviceMotionEvent.requestPermission() !== 'granted') throw new Error('Motion permission denied') } } catch (e) { return BB.toast(e.message, 'err') }
    BB.geo.start(); BB.ensureMic(); armed = true; armedT = Date.now(); cdPanel(); BB.toast('Crash detection is on') } }
addEventListener('devicemotion', e => { const a = e.accelerationIncludingGravity; if (!a || !armed) return; const m = Math.hypot(a.x, a.y, a.z), t = Date.now(); acc.push(m); if (acc.length > 200) acc.shift();
  if (!cur && !armedFlag && t > cool && t - armedT > 2000 && m > 25) { armedFlag = true; buf = []; peak = m / 9.81; setTimeout(check, 2500) } if (armedFlag) { buf.push(m); peak = Math.max(peak, m / 9.81) } });
let armedFlag = false;
function check() { armedFlag = false; const mean = buf.reduce((a, b) => a + b, 0) / buf.length, sd = Math.sqrt(buf.reduce((a, b) => a + (b - mean) ** 2, 0) / buf.length);
  if (sd < 1.2) { cool = Date.now() + 30000; trigger({speed_kmh: speedNow(), peak_g: peak, trace: acc.slice(-150).map(v => +(v / 9.81).toFixed(2)), source: 'phone'}) } }
function speedNow() { if (ride40) return 40; const l = BB.S.loc, r = BB.S.status && BB.S.status.ride; if (r && r.speed) return r.speed; return l && l.speed != null && l.t > Date.now() / 1000 - 15 ? l.speed : 0 }

async function trigger(e) { const l = BB.S.loc; if (l) { e.lat = l.lat; e.lon = l.lon }
  try { const o = await BB.post('/api/event', e); if (o.mode !== 'none') runIncident(o) } catch (x) { BB.err(x) } }
async function runIncident(o) { if (busyInc) return; busyInc = true; BB.S.quiet = true; const my = cur = {id: o.id, done: false, left: o.countdown_s || 30};
  const draw = () => ov(`<h1>${o.mode === 'crash' ? 'IMPACT DETECTED' : 'PHONE DROPPED?'}</h1><p>${esc(o.text)}</p><div class=cd id=cdn>${my.left}</div><p class=note>No answer in ${my.left} s: help is alerted.</p>
    <button class="btn go big" id=iok>I'M OK</button><button class="btn dng big" id=ihelp>SEND HELP NOW</button>`, o.mode === 'crash');
  draw(); const bind = () => { $('iok') && ($('iok').onclick = imOk); $('ihelp') && ($('ihelp').onclick = () => escalateNow('rider pressed send help')) }; bind();
  const tm = setInterval(async () => { if (my.done) return clearInterval(tm); my.left--; if ($('cdn')) { $('cdn').textContent = Math.max(0, my.left) } if (my.left <= 0) { clearInterval(tm); escalateNow('no response in time') } }, 1000);
  async function imOk() { my.done = true; clearInterval(tm); try { await BB.post('/api/cancel', {id: my.id}) } catch (x) {} end('Glad you are OK. Alert cancelled.') }
  async function escalateNow(why) { if (my.done) return; my.done = true; clearInterval(tm); try { const r = await BB.post('/api/escalate', {id: my.id, reason: why}); BB.say('', r) } catch (x) {} escalated(my.id) }
  try { await BB.say(o.text, o); if (my.done) return; BB.status('Listening... say "haan theek hoon" or "madad"', true); const blob = await BB.rec(6000, true); if (my.done || blob == null) return;   // no mic: the countdown and buttons still protect the rider
    
    const a = await BB.postForm('/api/answer', BB.form_(my.id, blob)); if (my.done) return; BB.status('You said: ' + (a.text || '(nothing)') + ' → ' + a.status.toUpperCase(), a.status === 'escalated');
    if (a.status === 'ok') { my.done = true; clearInterval(tm); BB.say('', a); end('Glad you are OK.') } else { my.done = true; clearInterval(tm); BB.say('', a); escalated(my.id, true) } } catch (x) { /* countdown still protects the rider */ } }
function end(msg) { OV.classList.remove('on', 'red'); busyInc = false; cur = null; BB.S.quiet = false; BB.toast(msg) }
function ov(html, red) { OV.innerHTML = html; OV.classList.add('on'); OV.classList.toggle('red', !!red) }

/* ---------- escalated view: what really happened, and what to do next ---------- */
async function escalated(id, speakBystander) { let poll;
  const show = async () => { let inc; try { inc = (await BB.get('/api/incidents')).find(i => i.id === id) } catch (e) { return }
    if (!inc || !OV.classList.contains('on')) { clearInterval(poll); return } const real = inc.notified.some(n => n.status === 'sent'), pending = inc.notified.some(n => n.status === 'pending'), noC = inc.notified.some(n => n.status === 'no_contacts');
    const url = inc.share && inc.share.url, msg = url ? contactsMsg(null, url) : '', cs = window.__contacts || [];
    ov(`<h1>${inc.mode === 'sos' ? 'SOS SENT' : 'HELP ALERTED'}</h1>
     <p>${inc.loc === 'none' ? 'No GPS fix yet, so your location is <b>unknown</b>.' : 'Location shared: ' + inc.lat.toFixed(4) + ', ' + inc.lon.toFixed(4)}${inc.loc === 'demo' ? ' (demo location)' : ''}</p>
     ${pending ? '<p class=note>Alerting contacts...</p>' : real ? '<p style="color:var(--g)">Messages were sent to your contacts.</p>' : `<p style="color:var(--o);font-weight:700">${noC ? 'You have no emergency contacts saved.' : 'Nothing was actually sent: no SMS service is configured on the server.'} Call for help or message from your phone below.</p>`}
     <div class=row style="justify-content:center"><a class="btn dng big" href="tel:112">CALL 112</a><a class="btn big" href="tel:108">CALL 108 AMBULANCE</a></div>
     ${url ? `<div class=row style="justify-content:center">${cs.map(c => `<a class="btn" href="sms:${esc(c.phone)}?body=${encodeURIComponent(msg)}">SMS ${esc(c.name)}</a><a class=btn target=_blank href="https://wa.me/${esc(c.phone.replace(/\D/g, ''))}?text=${encodeURIComponent(msg)}">WhatsApp ${esc(c.name)}</a>`).join('')}<button class=btn id=cpl>Copy tracking link</button></div>` : ''}
     ${inc.hospitals.length ? `<p class=note>Nearest hospital: ${esc(inc.hospitals[0].name || 'unnamed')}, ${(inc.hospitals[0].dist_m / 1000).toFixed(1)} km${inc.hospitals[0].phone ? ' · ' + esc(inc.hospitals[0].phone) : ''}</p>` : ''}
     <div class="panel list" style="max-width:520px;width:100%;text-align:left;max-height:24vh;overflow:auto">${inc.timeline.filter(t => t.who === 'system').slice(-6).map(t => `<div class=note>${t.t}s · ${esc(t.text)}</div>`).join('')}</div>
     <button class="btn go big" id=isafe>I'M SAFE: cancel alert</button>`, true);
    const cp = $('cpl'); if (cp) cp.onclick = () => navigator.clipboard && navigator.clipboard.writeText(url).then(() => BB.toast('Link copied'));
    $('isafe').onclick = async () => { clearInterval(poll); poll = null; try { await BB.post('/api/cancel', {id}) } catch (e) {} end('Alert cancelled. Contacts were told it was a false alarm.') } };
  try { window.__contacts = await BB.get('/api/contacts') } catch (e) {} busyInc = true; await show(); poll = setInterval(show, 2500);
  if (speakBystander) try { const sb = await BB.get('/api/say?k=by'); await BB.say('', sb); const b = await BB.rec(6000, true); if (b != null) await BB.postForm('/api/bystander', BB.form_(id, b)) } catch (e) {} }

/* ---------- SOS ---------- */
function startSOS() { BB.S.quiet = true; let n = 5, dead = false; BB.geo.start();
  const draw = () => ov(`<h1>SOS</h1><p>Alerting your contacts in</p><div class=cd>${n}</div><button class="btn big" id=scn>CANCEL</button>`, true); draw();
  $('scn').onclick = () => { dead = true; clearInterval(t); end('SOS cancelled.') };
  const t = setInterval(async () => { if (dead) return; n--; if (n > 0) return draw(); clearInterval(t); try { const l = BB.S.loc, r = await BB.post('/api/sos', l ? {lat: l.lat, lon: l.lon} : {}); BB.say(r.text, r); escalated(r.id) } catch (e) { ov(`<h1>COULD NOT REACH THE SERVER</h1><p>Call 112 now.</p><a class="btn dng big" href="tel:112">CALL 112</a><button class="btn big" id=cx>Close</button>`, true); $('cx').onclick = () => end('Closed'); } }, 1000) }
$('sos').onclick = startSOS; BB.actions.sos = startSOS;

/* ---------- live location sharing ---------- */
async function loadShares() { let s = []; try { s = await BB.get('/api/shares') } catch (e) {}
  $('shp').innerHTML = `<h2>Share live location</h2>` + (s.length ? s.map(x => `<div class=li><div class=grow><small>Anyone with this link can see where you are until you stop sharing (expires ${BB.f.time(x.expires)}).</small><input readonly value="${esc(x.url)}" onclick="this.select()"></div></div><div class=row style="margin-top:8px"><button class=btn data-c="${esc(x.url)}">Copy</button>${navigator.share ? `<button class=btn data-s="${esc(x.url)}">Share...</button>` : ''}<button class="btn dng" data-x="${x.token}">Stop sharing</button></div>`).join('')
    : `<p class=note>Create a private link your family can open in a browser. It shows your position on a map, updated every few seconds, and stops when you tap Stop.</p><button class="btn pri" id=shs style="width:100%">Start sharing</button>`);
  const q = a => $('shp').querySelectorAll(a);
  q('[data-c]').forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.c).then(() => BB.toast('Link copied'))); q('[data-s]').forEach(b => b.onclick = () => navigator.share({title: 'Bike Buddy live location', url: b.dataset.s}).catch(() => {}));
  q('[data-x]').forEach(b => b.onclick = async () => { try { await BB.post('/api/share/stop', {token: b.dataset.x}); loadShares() } catch (e) { BB.err(e) } });
  const st = $('shs'); if (st) st.onclick = async () => { BB.geo.start(); try { const l = BB.S.loc; await BB.post('/api/share/start', l ? {lat: l.lat, lon: l.lon} : {}); loadShares(); if (!l) BB.toast('Waiting for GPS. The link will show your position as soon as it is available.', 'warn', 6000) } catch (e) { BB.err(e) } };
}
BB.actions.share = () => { BB.tab('safety'); BB.post('/api/share/start', BB.ctx()).then(loadShares).catch(BB.err) };

/* ---------- contacts ---------- */
async function loadContacts() { let c = [], st = BB.S.status; try { c = await BB.get('/api/contacts') } catch (e) {} window.__contacts = c; const ch = st && st.channels || [];
  $('ctp').innerHTML = `<div class=row><h2 class=grow style="margin:0">Emergency contacts</h2><button class="btn sm" id=cad>+ Add</button></div>
   <p class=note style="margin:8px 0">${ch.length ? 'Alerts are sent by: ' + ch.join(', ') + '.' : '<b style="color:var(--o)">No SMS/webhook is configured on the server</b>, so alerts to contacts are <b>simulated</b>. In an emergency you will get buttons to message them from your own phone. See README to enable real SMS.'}</p>
   <div class=list>${c.length ? c.map(x => `<div class=li><div class=grow><b>${esc(x.name)}</b><small>${esc(x.phone)}</small></div><a class="btn sm" href="tel:${esc(x.phone)}">Call</a><button class="btn sm dng" data-d=${x.id}>✕</button></div>`).join('') : '<div class=empty>No contacts yet. Add up to 5.</div>'}</div>`;
  $('cad').onclick = () => BB.form('Add emergency contact', [{k: 'name', label: 'Name', req: 1, ph: 'Mom'}, {k: 'phone', label: 'Phone number', req: 1, ph: '98765 43210', type: 'tel'}], async v => { await BB.post('/api/contacts', v); loadContacts() });
  $('ctp').querySelectorAll('[data-d]').forEach(b => b.onclick = () => BB.confirm('Remove this contact?', async () => { try { await BB.del('/api/contacts/' + b.dataset.d); loadContacts() } catch (e) { BB.err(e) } })) }

/* ---------- hospitals, numbers, history ---------- */
async function loadHospitals() { const l = BB.S.loc; if (!l) { $('hsp').innerHTML = '<h2>Nearest hospitals</h2><p class=note>Waiting for your location. <button class="btn sm" id=hgl>Allow location</button></p>'; $('hgl').onclick = () => { BB.geo.start(); BB.once('loc', loadHospitals) }; return }
  try { const r = await BB.get(`/api/nearby?kind=hospital&lat=${l.lat}&lon=${l.lon}&limit=4`); $('hsp').innerHTML = `<h2>Nearest hospitals</h2>${r.stale ? `<div class=pill-warn>Offline: saved result from ${Math.round(r.age_s / 60)} min ago.</div>` : ''}<div class=list>${r.items.map(p => `<div class=li><div class=grow><b>${esc(p.name || 'Hospital (unnamed)')}</b><small>${(p.dist_m / 1000).toFixed(1)} km</small></div>${p.phone ? `<a class="btn sm" href="tel:${esc(p.phone.replace(/[^\d+]/g, ''))}">Call</a>` : ''}<button class="btn sm go" data-i="${p.lat},${p.lon},${esc(p.name || 'Hospital')}">Go</button></div>`).join('') || '<div class=empty>None found nearby.</div>'}</div>`;
    $('hsp').querySelectorAll('[data-i]').forEach(b => b.onclick = () => { const [la, lo, ...n] = b.dataset.i.split(','); BB.tab('map'); BB.nav.route({lat: +la, lon: +lo, name: n.join(',')}) }) } catch (e) { $('hsp').innerHTML = `<h2>Nearest hospitals</h2><div class=empty>${e.status === 503 || e.message === 'offline' ? 'Cannot look up hospitals without internet. Call 108 or 112.' : esc(e.message)}</div>` } }
async function loadIncs() { try { const d = await BB.get('/api/incidents'); $('incs').innerHTML = d.length ? d.slice(0, 5).map(i => `<div class=li><div class=grow><b>${i.mode.toUpperCase()}</b> <span class="st ${i.status === 'escalated' ? 'overdue' : 'ok'}">${i.status.replace('_', ' ')}</span><small>${esc(i.summary)}</small></div></div>`).join('') : '<div class=empty>No alerts since the server started.</div>' } catch (e) {} }
$('nums').innerHTML = [['112', 'Emergency'], ['108', 'Ambulance'], ['100', 'Police'], ['101', 'Fire']].map(([n, l]) => `<a class=tile href="tel:${n}"><b>${n}</b>${l}</a>`).join('');

/* ---------- tests ---------- */
$('r40').onchange = e => ride40 = e.target.checked;
$('tcr').onclick = () => { BB.geo.start(); trigger({speed_kmh: 40, peak_g: 4.5, source: 'phone_sim', trace: [1, 1, 1, 4.5, 2, 1.4, 1.1, 1, 1]}) };
$('tbk').onclick = async () => { try { BB.geo.start(); runIncident(await BB.post('/api/sim')) } catch (e) { BB.err(e) } };

BB.tabs.safety = () => { cdPanel(); loadShares(); loadContacts(); loadHospitals(); loadIncs() }; BB.on('online', () => BB.S.tab === 'safety' && BB.tabs.safety());
BB.on('status', st => { $('sdot').style.display = armed || st.sharing ? 'none' : 'block' }); cdPanel();
})();
