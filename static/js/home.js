/* Home: greeting, stat cards, live bike data with source badges, proactive alerts, Talk-to-Buddy orb, hands-free mode, demo tools, 3D bike. */
(() => {
const SENS = [['tyre_front', 'Front PSI', ''], ['tyre_rear', 'Rear PSI', ''], ['fuel', 'Fuel', '%'], ['engine_temp', 'Engine', '°C']];
const hasData = (st, k) => { const v = st.state[k]; if (v == null) return false; const m = st.src[k]; return !(st.conn.mode === 'live' && (!m || m.age == null || m.age > 60)) };
const alertKeys = st => new Set(st.alerts.active.map(a => a.key));
const card = (label, val, unit, src, bad) => `<div class="k ${bad ? 'bad' : ''} ${val == null ? 'na' : ''}"><small>${label}</small>${val == null ? '<b>n/a</b>' : `<b>${esc(val)}<em>${unit}</em></b>`}<div style="margin-top:6px">${val == null ? BB.badge('none') : BB.badge(src)}</div></div>`;

function render(st) {
  const s = st.state, ak = alertKeys(st), act = st.alerts.active, sim = st.conn.status === 'simulated', rider = BB.S.settings.rider || 'Rider', h = new Date().getHours();
  $('greet').textContent = h < 12 ? 'GOOD MORNING, ' + rider.toUpperCase() : h < 17 ? 'GOOD AFTERNOON, ' + rider.toUpperCase() : 'GOOD EVENING, ' + rider.toUpperCase();
  const worst = act.some(a => a.level === 'critical') ? 'critical' : act.length ? 'warn' : 'ok';
  const any = ['battery', 'engine_temp', 'fuel', 'tyre_front', 'tyre_rear'].some(k => hasData(st, k));
  $('hello').innerHTML = `Hello, ${esc(rider)}!<small>${!any && !sim ? 'No live sensor data right now.' : worst === 'ok' ? 'Your motorcycle is looking healthy.' : act.length + (act.length === 1 ? ' thing needs' : ' things need') + ' your attention.'}${sim ? ' (demo data)' : ''}</small>`;
  const b = $('demoBanner'); b.hidden = !(sim || st.bike.demo);
  b.innerHTML = (sim ? '<b>DEMO MODE.</b> Bike readings below are simulated. Connect a real bike with <code>bridge.py</code> or <code>POST /api/telemetry</code>. GPS, rides and garage data are real. ' : '') + (st.bike.demo ? '<b>Sample bike.</b> Edit its details in Garage.' : '');
  const lv = st.ride, l = BB.S.loc, spd = lv ? lv.speed : (l && l.speed != null && l.t > Date.now() / 1000 - 15 ? Math.round(l.speed) : null);
  $('cards').innerHTML = card('Battery', hasData(st, 'battery') ? s.battery : null, ' V', st.src.battery && st.src.battery.src, ak.has('batt'))
    + (lv ? card('Distance', lv.dist_km, ' km', 'gps') : card('Trip', s.trip == null ? null : (+s.trip).toFixed(1), ' km', st.src.trip && st.src.trip.src))
    + card('Speed', spd, ' km/h', 'gps')
    + `<div class="k ${worst === 'critical' ? 'bad' : ''} ${!any ? 'na' : ''}"><small>Bike health</small><b style="color:${worst === 'ok' ? 'var(--g)' : worst === 'warn' ? 'var(--o)' : 'var(--r)'}">${!any && !act.length ? 'n/a' : worst === 'ok' ? 'Good' : worst === 'warn' ? 'Check' : 'Alert'}</b>${BB.badge('estimate')}</div>`;
  $('sens').innerHTML = SENS.map(([k, l, u]) => card(l, hasData(st, k) ? s[k] : null, u ? ' ' + u : '', st.src[k] && st.src[k].src, ak.has(k) || (k === 'fuel' && ak.has('fuel')) || (k === 'engine_temp' && ak.has('temp')))).join('');
  $('alerts').innerHTML = act.length ? act.map(a => `<div class="al ${a.level}"><div class=grow><b>${a.level.toUpperCase()} · ${new Date(a.since * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</b>${esc(a.text)}</div>${BB.badge(a.src)}</div>`).join('') : '<div class=ok-line>No active alerts. Buddy will speak up if something changes.</div>';
  $('bn').textContent = BB.S.settings.name; $('sub').textContent = 'ASK ' + BB.S.settings.name.toUpperCase();
  $('tMode').textContent = 'Mode: ' + (st.conn.mode === 'live' ? 'live' : 'demo');
  $('vdot').style.display = act.length || st.alerts.active.some(a => a.key.startsWith('svc') || a.key === 'oil') ? 'block' : 'none';
  scene.bad(ak);
}
BB.on('status', render); BB.on('loc', () => BB.S.status && render(BB.S.status)); BB.on('settings', () => BB.S.status && render(BB.S.status));

/* ---------- orb ---------- */
let busy = false;
$('orb').onclick = async () => { if (busy) return; busy = true;
  try { BB.geo.start(); BB.status('Listening... ask about your bike, ride, fuel or service'); $('orb').classList.add('rec'); const b = await BB.rec(5000); $('orb').classList.remove('rec'); await BB.ask(b) }
  catch (e) { BB.status(e.message === 'offline' ? 'Server offline. Reconnecting...' : e.message, true) } finally { busy = false; $('orb').classList.remove('rec') } };
$('pre').onclick = async () => { try { const o = await BB.post('/api/precheck'); BB.status(o.reply, o.warnings > 0); BB.say(o.reply, o) } catch (e) { BB.err(e) } };

/* ---------- hands-free ("Buddy, is my bike healthy?") ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition, HF = {on: false, rec: null};
const wakeWords = () => [BB.S.settings.name.toLowerCase(), 'hey buddy', 'ok buddy', 'buddy', 'बडी', 'बड्डी', 'ಬಡ್ಡಿ'];
const TAG = {hinglish: 'en-IN', english: 'en-IN', hindi: 'hi-IN', kannada: 'kn-IN'};
function hfStart() {
  const r = HF.rec = new SR(); r.continuous = true; r.interimResults = false; r.lang = TAG[BB.S.settings.lang] || 'en-IN';
  r.onresult = async e => { const t = e.results[e.results.length - 1][0].transcript.toLowerCase().trim(); if (BB.speaking || busy) return;
    let at = -1, len = 0; for (const w of wakeWords()) { const i = t.indexOf(w); if (i >= 0 && i < 30 && (at < 0 || i < at)) { at = i; len = w.length } }
    if (at < 0) return; const cmd = t.slice(at + len).replace(/^[,.\s]+/, ''); busy = true;
    try { BB.geo.start(); if (cmd.length > 2) await BB.ask(cmd); else { BB.status('Yes? Listening...'); $('orb').classList.add('rec'); const b = await BB.rec(5000); $('orb').classList.remove('rec'); await BB.ask(b) } }
    catch (x) { BB.err(x) } finally { busy = false } };
  r.onerror = e => { if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { HF.on = false; hfLabel(); BB.toast('Microphone permission denied for hands-free.', 'err') } };
  r.onend = () => { if (HF.on) setTimeout(() => { try { r.start() } catch (x) {} }, 400) };
  try { r.start() } catch (x) {} }
const hfLabel = () => { $('hf').textContent = 'Hands-free: ' + (HF.on ? 'on' : 'off'); $('hf').classList.toggle('go', HF.on) };
$('hf').onclick = () => { if (!SR) return BB.toast('Hands-free needs a browser with speech recognition (Chrome or Edge). The orb still works everywhere.', 'warn', 7000);
  HF.on = !HF.on; hfLabel(); if (HF.on) { hfStart(); BB.toast(`Say "${BB.S.settings.name}, ..." then your question. The page must stay open and on screen.`, 'info', 7000) } else { try { HF.rec.stop() } catch (x) {} } };

/* ---------- demo tools ---------- */
const setv = (o, m) => async () => { try { for (const x of [].concat(o)) await BB.post('/api/bike/set', x); BB.toast(m); BB.poll() } catch (e) { BB.err(e) } };
$('tTyre').onclick = setv({tyre_front: 19}, 'Simulated low front tyre');
$('tPunc').onclick = setv([{tyre_front: 30}, {tyre_front: 23}], 'Simulated sudden pressure drop');
$('tBatt').onclick = setv({battery: 11.7}, 'Simulated low battery');
$('tHot').onclick = setv({engine_temp: 112}, 'Simulated hot engine');
$('tFuel').onclick = setv({fuel: 6}, 'Simulated low fuel');
$('tReset').onclick = setv({battery: 12.6, engine_temp: 88, fuel: 62, tyre_front: 30, tyre_rear: 32}, 'Simulated values reset');
$('tSeed').onclick = async () => { try { const r = await BB.post('/api/demo/seed'); BB.toast(`Added ${r.rides} simulated rides (marked SIM)`); BB.emit('data') } catch (e) { BB.err(e) } };
$('tClear').onclick = async () => { try { await BB.post('/api/demo/clear'); BB.toast('Simulated rides and battery history removed'); BB.emit('data') } catch (e) { BB.err(e) } };
$('tMode').onclick = () => { const live = BB.S.status && BB.S.status.conn.mode === 'live';
  const go = async m => { try { await BB.post('/api/mode', {mode: m}); BB.poll() } catch (e) { BB.err(e) } };
  live ? go('sim') : BB.confirm('Switch to live mode? All demo readings are cleared and the app shows n/a until a real bike sends data.', () => go('live')) };

/* ---------- 3D bike (three.js, procedural). If the library cannot load, the rest of the app still works. ---------- */
const scene = (() => {
  if (!window.THREE) { $('fb').style.display = 'grid'; return {bad() {}} }
  const cv = $('c'), RN = new THREE.WebGLRenderer({canvas: cv, antialias: true, alpha: true}); RN.setPixelRatio(Math.min(devicePixelRatio, 2));
  const S = new THREE.Scene(); S.fog = new THREE.FogExp2(0x05070b, .05); const cam = new THREE.PerspectiveCamera(45, 1, .1, 100);
  const fit = () => { const w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return; RN.setSize(w, h, false); cam.aspect = w / h; cam.position.set(3.6, 1.8, w < 640 ? 7.2 : 4.6); cam.lookAt(0, .75, 0); cam.updateProjectionMatrix() };
  addEventListener('resize', fit); BB.on('tab', t => t === 'home' && setTimeout(fit, 30)); setTimeout(fit, 50);
  S.add(new THREE.AmbientLight(0x7799bb, .8)); const dl = new THREE.DirectionalLight(0xffffff, .9); dl.position.set(4, 6, 3); S.add(dl);
  const p1 = new THREE.PointLight(0x00e5ff, 1.6, 14); p1.position.set(-3, 2, 2); S.add(p1); const p2 = new THREE.PointLight(0xff8a00, 1.4, 14); p2.position.set(3, 1, -3); S.add(p2);
  S.add(new THREE.GridHelper(40, 80, 0x00e5ff, 0x0f2a3a));
  const ring = new THREE.Mesh(new THREE.RingGeometry(2.3, 2.38, 80), new THREE.MeshBasicMaterial({color: 0x00e5ff, side: 2, transparent: true, opacity: .7})); ring.rotation.x = -Math.PI / 2; ring.position.y = .02; S.add(ring);
  const TYPES = {sport: {wb: 2.1, R: .52, col: 0xff2a2a, tank: [.45, .2, .2], scoot: 0}, cruiser: {wb: 2.7, R: .62, col: 0xff8a00, tank: [.55, .28, .27], scoot: 0}, scooter: {wb: 1.55, R: .36, col: 0x00e5ff, tank: [.3, .16, .2], scoot: 1}};
  const M = (c, e) => new THREE.MeshStandardMaterial({color: c, metalness: .65, roughness: .3, emissive: e || 0, emissiveIntensity: .15}), V = (x, y, z) => new THREE.Vector3(x, y, z);
  const bar = (a, b, r, m) => { const d = V(0, 0, 0).subVectors(b, a), L = d.length(), o = new THREE.Mesh(new THREE.CylinderGeometry(r, r, L, 12), m); o.position.copy(a).addScaledVector(d, .5); o.quaternion.setFromUnitVectors(V(0, 1, 0), d.normalize()); return o };
  let bike = new THREE.Group(), parts = {}, wheels = []; S.add(bike);
  function build(k) { S.remove(bike); const T = TYPES[k], R = T.R, wb = T.wb, g = new THREE.Group(); parts = {}; wheels = [];
    const dark = M(0x1a1f2b), chrome = M(0xaab6c6), body = M(T.col), tag = (m, n) => { m.userData.part = n; (parts[n] = parts[n] || []).push(m); return m };
    const wheel = (x, n) => { const w = new THREE.Group(); w.add(tag(new THREE.Mesh(new THREE.TorusGeometry(R, R * .2, 16, 48), M(0x151a22, 0x00e5ff)), n), new THREE.Mesh(new THREE.TorusGeometry(R * .8, .02, 8, 48), M(0x00e5ff, 0x00e5ff)));
      for (let i = 0; i < 4; i++) { const s = new THREE.Mesh(new THREE.BoxGeometry(R * 1.6, .014, .014), chrome); s.rotation.z = i * Math.PI / 4; w.add(s) } w.position.set(x, R, 0); g.add(w); wheels.push(w) };
    wheel(wb / 2, 'tyre_front'); wheel(-wb / 2, 'tyre_rear');
    const fh = V(wb / 2, R, 0), rh = V(-wb / 2, R, 0), head = V(wb * .3, R * 2 + .35, 0), seat = V(-wb * .22, R * 2 + .2, 0), eng = V(0, R + .3, 0);
    [[head, fh, .04], [rh, eng, .05]].forEach(a => g.add(bar(a[0], a[1], a[2], chrome))); [[head, eng], [head, seat], [seat, rh]].forEach(a => g.add(tag(bar(a[0], a[1], .04, body), 'frame')));
    const tk = tag(new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), body), 'tank'); tk.scale.set(...T.tank); tk.position.set(wb * .1, R * 2 + .3, 0); g.add(tk);
    const en = tag(new THREE.Mesh(new THREE.BoxGeometry(.55, .4, .36), dark), 'engine'); en.position.copy(eng); g.add(en);
    const bt = tag(new THREE.Mesh(new THREE.BoxGeometry(.24, .18, .26), M(0x222a36)), 'battery'); bt.position.set(-wb * .26, R + .55, 0); g.add(bt);
    const st_ = new THREE.Mesh(new THREE.BoxGeometry(.75, .09, .3), dark); st_.position.copy(seat); g.add(st_); g.add(bar(V(head.x - .1, head.y + .12, -.36), V(head.x - .1, head.y + .12, .36), .03, chrome));
    const hl = new THREE.Mesh(new THREE.SphereGeometry(.1, 16, 12), M(0xffffaa, 0xffee88)); hl.position.set(head.x + .16, head.y, 0); g.add(hl); g.add(bar(V(-wb * .1, R * .7, .2), V(-wb * .6, R * .9, .2), .05, chrome));
    if (T.scoot) { const b = new THREE.Mesh(new THREE.BoxGeometry(wb * .8, .32, .5), body); b.position.set(0, R + .2, 0); g.add(b) } bike = g; S.add(bike) }
  const setPart = (n, bad) => (parts[n] || []).forEach(m => { m.material.emissive.setHex(bad ? 0xff2020 : 0x00e5ff); m.material.emissiveIntensity = bad ? 1.2 : (n.startsWith('tyre') ? .3 : .15) });
  document.querySelectorAll('#veh button').forEach(b => b.onclick = () => { document.querySelectorAll('#veh button').forEach(x => x.classList.remove('on')); b.classList.add('on'); build(b.dataset.k); BB.S.status && render(BB.S.status) }); build('sport');
  const PH = {tyre_front: 'tyre pressure', tyre_rear: 'tyre pressure', tank: 'how much petrol', engine: 'engine temperature', battery: 'battery', frame: 'when is my next service'};
  const ray = new THREE.Raycaster(), mv = new THREE.Vector2(); let drag = false, moved = 0, lx = 0, pause = 0;
  cv.addEventListener('pointerdown', e => { drag = true; moved = 0; lx = e.clientX });
  addEventListener('pointermove', e => { if (!drag) return; const d = e.clientX - lx; lx = e.clientX; moved += Math.abs(d); bike.rotation.y += d * .01; pause = performance.now() + 3000 });
  addEventListener('pointerup', async e => { if (!drag) return; drag = false; if (moved > 6) return; const r = cv.getBoundingClientRect(); mv.set((e.clientX - r.left) / r.width * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(mv, cam);
    const h = ray.intersectObjects([].concat(...Object.values(parts)), false)[0]; if (!h) return;
    try { const o = await BB.post('/api/asktext', {text: PH[h.object.userData.part], ...BB.ctx()}); BB.status(o.reply); BB.say(o.reply, o) } catch (x) { BB.err(x) } });
  const loop = t => { requestAnimationFrame(loop); if (BB.S.tab !== 'home') return; const s = t / 1000, lv = BB.S.status && BB.S.status.ride; wheels.forEach(w => w.rotation.z -= .02 + (lv ? Math.min(.15, lv.speed / 400) : 0));
    if (!drag && t > pause) bike.rotation.y += .004; bike.position.y = Math.sin(s * 1.5) * .025; ring.rotation.z = s * .3; $('orb').style.setProperty('--k', 1 + (BB.speaking ? .07 * Math.sin(s * 14) : 0)); RN.render(S, cam) };
  requestAnimationFrame(loop);
  return {bad(ak) { setPart('tyre_front', ak.has('tyre_front')); setPart('tyre_rear', ak.has('tyre_rear')); setPart('tank', ak.has('fuel')); setPart('battery', ak.has('batt')); setPart('engine', ak.has('temp')); setPart('frame', ak.has('svc')) }};
})();
})();
