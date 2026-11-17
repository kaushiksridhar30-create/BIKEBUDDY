/* Rides: live GPS tracking (with offline queue), demo ride, ride history with route + events, analytics (weekly/monthly report, eco score, speed trend, behaviour insights). */
(() => {
const V = $('v-ride'); let active = false, source = 'gps', buf = [], flushT = null, wake = null, demoT = null, days = 7, lastKey = '';
V.innerHTML = `<div id=rl></div><h2 style="margin-top:18px">Analytics</h2><div class=row style="margin-bottom:10px"><div class=seg id=per><button data-d=7 class=on>7 days</button><button data-d=30>30 days</button></div></div><div id=an></div><h2 style="margin-top:18px">Ride history</h2><div id=hist class="panel list"></div>`;
const simTag = s => s === 'sim' ? '<span class=sim-tag>SIM</span>' : '';

/* ---------- live ride card ---------- */
function liveCard(st) {
  const lv = st.ride, el = $('rl');
  if (!lv) { el.innerHTML = `<div class=panel><h2>Track a ride</h2><p class=note>Uses your phone's GPS: distance, speed, route and harsh braking. Keep this page open and on screen while riding.</p>
   <div class=row><button class="btn pri grow" id=rs>Start ride</button><button class=btn id=rd>Demo ride</button></div><p class=note id=rm></p></div>`;
    $('rs').onclick = () => start('gps'); $('rd').onclick = () => demo(); return }
  el.innerHTML = `<div class=panel style="border-color:var(--g)"><div class=row><h2 class=grow style="margin:0">Ride in progress ${simTag(lv.source)}</h2>${BB.badge(lv.source === 'sim' ? 'sim' : 'gps')}</div>
   <div class=stat-big style="margin:14px 0"><div><b>${BB.f.km(lv.dist_km)}</b><small>KM</small></div><div><b>${lv.speed}</b><small>KM/H</small></div><div><b style="font-size:22px">${BB.f.dur(lv.duration_s)}</b><small>TIME</small></div></div>
   <div class=row note style="color:var(--mut)"><span class=grow>Avg ${lv.avg_kmh} · Max ${lv.max_kmh} km/h · ${lv.events} harsh events</span><span class=note>${BB.S.online ? '' : 'offline: saving points on this phone'}${BB.q.get().length ? ` (${BB.q.get().reduce((a, b) => a + b.pts.length, 0)} queued)` : ''}</span></div>
   <button class="btn dng" style="width:100%;margin-top:12px" id=re>Stop ride</button></div>`;
  $('re').onclick = stop;
}
BB.on('status', st => { if (st.ride && !active) { active = true; source = st.ride.source; if (source === 'gps') { BB.geo.start(); keepAwake() } }
  if (!st.ride && active && !demoT) { active = false } const k = JSON.stringify([st.ride, BB.S.online]); if (k !== lastKey || !st.ride) { lastKey = k; liveCard(st) } });

async function start(src) {
  try { if (src === 'gps' && !BB.geo.start()) return BB.toast('This browser has no GPS access.', 'err');
    await BB.post('/api/ride/start', {source: src}); active = true; source = src; buf = []; if (src === 'gps') { keepAwake(); BB.toast('Ride started. Ride safe.') } BB.poll(); } catch (e) { BB.err(e) } }
BB.actions.ride_start = () => { if (!active) { active = true; source = 'gps'; BB.geo.start(); keepAwake(); BB.poll() } };
BB.actions.ride_stop = () => { active = false; releaseWake(); BB.poll(); loadHist(); loadAn() };

BB.on('loc', l => { if (!active || source !== 'gps') return; if (buf.length && buf[buf.length - 1].t === l.t) return;
  buf.push({t: l.t, lat: l.lat, lon: l.lon, speed: l.speed == null ? null : +l.speed.toFixed(1), acc: l.acc}); if (!flushT) flushT = setTimeout(flush, 3000) });
async function flush() { flushT = null; if (!buf.length) return; const b = buf; buf = []; try { const r = await BB.postPoints(b, source); if (r && r.live) BB.S.status && (BB.S.status.ride = r.live) } catch (e) { BB.err(e) } }
async function stop() { try { await flush(); clearInterval(demoT); demoT = null; const r = await BB.post('/api/ride/stop', {}); active = false; releaseWake(); BB.poll(); summary(r.ride, r.saved); loadHist(); loadAn() } catch (e) { BB.err(e) } }
function summary(r, saved) { if (!r) return; BB.modal(`<h2>Ride ${saved ? 'saved' : 'too short, not saved'} ${simTag(r.source)}</h2><div class=stat-big style="margin:12px 0"><div><b>${BB.f.km(r.dist_km)}</b><small>KM</small></div><div><b>${r.avg_kmh}</b><small>AVG KM/H</small></div><div><b>${r.max_kmh}</b><small>MAX KM/H</small></div></div>
  <p>Duration ${BB.f.dur(r.duration_s)} · ${r.harsh_brake} sudden brakes · ${r.harsh_accel} hard accelerations${r.eco != null ? ` · eco score ${r.eco}/100 ${BB.badge('estimate')}` : ''}</p>${saved && r.source === 'gps' && BB.S.settings.auto_odo !== false ? '<p class=note>Distance added to your odometer (estimate).</p>' : ''}<button class="btn pri" style="width:100%" onclick="BB.close()">Done</button>`) }

/* wake lock keeps the screen on so GPS keeps flowing (best effort; browsers cannot track in the background) */
async function keepAwake() { try { if (navigator.wakeLock && !wake) { wake = await navigator.wakeLock.request('screen'); wake.onrelease = () => wake = null } } catch (e) {} }
function releaseWake() { try { wake && wake.release() } catch (e) {} wake = null }
document.addEventListener('visibilitychange', () => { if (!document.hidden && active && source === 'gps') keepAwake() });

/* ---------- demo ride: replays a generated GPS trace through the SAME server pipeline, marked simulated ---------- */
async function demo() {
  try { const pts = await BB.get('/api/demo/route?minutes=5'); await BB.post('/api/ride/start', {source: 'sim'}); active = true; source = 'sim'; let i = 0; const t0 = Date.now() / 1000 - pts.length;
    BB.toast('Demo ride running (simulated GPS, replayed 10x faster)'); BB.poll();
    demoT = setInterval(async () => { const chunk = pts.slice(i, i += 10).map(p => ({t: t0 + p.dt, lat: p.lat, lon: p.lon, speed: p.speed, acc: 6}));
      if (!chunk.length) { clearInterval(demoT); demoT = null; return stop() } try { const r = await BB.post('/api/ride/point', {points: chunk, source: 'sim'}); BB.S.status.ride = r.live; liveCard(BB.S.status) } catch (e) {} }, 1000) } catch (e) { BB.err(e) } }

/* ---------- charts (plain SVG, no library) ---------- */
function bars(series) { const W = 640, H = 170, p = 26, m = Math.max(5, ...series.map(s => s.km)), bw = (W - p * 2) / series.length;
  return `<svg class=chart viewBox="0 0 ${W} ${H}" role=img aria-label="Distance per day"><line x1=${p} x2=${W - p} y1=${H - 26} y2=${H - 26} stroke="#00e5ff33" />
   ${series.map((s, i) => { const h = s.km / m * (H - 56), x = p + i * bw + bw * .15; return `<g><rect x=${x} y=${H - 26 - h} width=${bw * .7} height=${Math.max(h, s.km ? 2 : 0)} rx=3 fill="${s.km ? 'var(--c)' : 'transparent'}"><title>${s.date}: ${s.km} km, ${s.rides} rides</title></rect>${s.km ? `<text x=${x + bw * .35} y=${H - 30 - h} text-anchor=middle>${s.km}</text>` : ''}${series.length <= 7 || i % 5 === 0 ? `<text x=${x + bw * .35} y=${H - 8} text-anchor=middle>${new Date(s.date + 'T00:00').toLocaleDateString([], series.length <= 7 ? {weekday: 'short'} : {day: 'numeric', month: 'short'})}</text>` : ''}</g>` }).join('')}</svg>` }
function line(pts, key, unit) { if (pts.length < 2) return '<div class=empty>Needs at least 2 rides.</div>'; const W = 640, H = 150, p = 30, vs = pts.map(x => x[key]), mn = Math.min(...vs) - 3, mx = Math.max(...vs) + 3;
  const X = i => p + i * (W - p * 2) / (pts.length - 1), Y = v => H - 22 - (v - mn) / (mx - mn) * (H - 40);
  return `<svg class=chart viewBox="0 0 ${W} ${H}" role=img aria-label="Speed trend"><polyline fill=none stroke="var(--o)" stroke-width=2.5 points="${pts.map((x, i) => X(i) + ',' + Y(x[key])).join(' ')}" />${pts.map((x, i) => `<circle cx=${X(i)} cy=${Y(x[key])} r=4 fill="${x.source === 'sim' ? 'var(--bg)' : 'var(--o)'}" stroke="var(--o)" stroke-width=2><title>${BB.f.date(x.start)}: ${x[key]} ${unit}${x.source === 'sim' ? ' (simulated)' : ''}</title></circle>`).join('')}
   <text x=4 y=${Y(vs[0]) < 20 ? 20 : 14}>${Math.round(mx)}</text><text x=4 y=${H - 22}>${Math.round(mn)}</text></svg>` }
function gauge(score) { const c = score == null ? 'var(--mut)' : score >= 75 ? 'var(--g)' : score >= 50 ? 'var(--y)' : 'var(--r)', L = 251, o = score == null ? L : L * (1 - score / 100);
  return `<svg viewBox="0 0 200 120" style="width:170px;display:block;margin:0 auto"><path d="M20 100A80 80 0 0 1 180 100" fill=none stroke="#ffffff18" stroke-width=14 stroke-linecap=round /><path d="M20 100A80 80 0 0 1 180 100" fill=none stroke="${c}" stroke-width=14 stroke-linecap=round stroke-dasharray=${L} stroke-dashoffset=${o} />
   <text x=100 y=92 text-anchor=middle style="font:800 34px Orbitron;fill:${c}">${score == null ? '--' : score}</text><text x=100 y=112 text-anchor=middle style="font:600 11px Orbitron;fill:var(--mut)">ECO SCORE / 100</text></svg>` }

async function loadAn() {
  try { const a = await BB.get('/api/analytics?days=' + days), r = a.report, el = $('an');
    if (!r.rides) { el.innerHTML = '<div class="panel empty">No rides in this period yet. Track a ride, or add demo rides from the Home screen tools.</div>'; return }
    const ch = r.km_change_pct == null ? '' : `<span style="color:${r.km_change_pct >= 0 ? 'var(--g)' : 'var(--o)'}">${r.km_change_pct >= 0 ? '+' : ''}${r.km_change_pct}% vs previous ${days} days</span>`;
    el.innerHTML = `${r.sim_rides ? `<div class=pill-warn>${r.sim_rides} of these ${r.rides} rides are <b>simulated</b> demo rides (marked SIM).</div>` : ''}
     <div class=cards style="grid-template-columns:repeat(3,1fr)"><div class=k><small>Rides</small><b>${r.rides}</b></div><div class=k><small>Distance</small><b>${r.km}<em>km</em></b><div style="margin-top:6px">${BB.badge('gps')}</div></div><div class=k><small>Avg speed</small><b>${r.avg_kmh}<em>km/h</em></b><div style="margin-top:6px">${BB.badge('gps')}</div></div>
      <div class=k><small>Sudden brakes</small><b>${r.harsh_brake}</b><div style="margin-top:6px">${BB.badge('gps')}</div></div><div class=k><small>Hard accel</small><b>${r.harsh_accel}</b><div style="margin-top:6px">${BB.badge('gps')}</div></div><div class=k><small>Top speed</small><b>${r.max_kmh}<em>km/h</em></b><div style="margin-top:6px">${BB.badge('gps')}</div></div></div>
     <div class=panel><h3 style="margin-top:0">Distance per day ${ch}</h3>${bars(r.series)}</div>
     <div class=grid2><div class=panel><h3 style="margin-top:0">Eco riding score ${BB.badge('estimate')}</h3>${gauge(r.eco)}<p class=note style="text-align:center">Estimate from smoothness, hard braking and time over your speed limit. Not measured fuel use.</p></div>
      <div class=panel><h3 style="margin-top:0">Speed trend ${a.speed_trend.trend ? `· <span style="color:var(--c)">${a.speed_trend.trend}</span>` : ''}</h3>${line(a.speed_trend.points, 'avg', 'km/h')}<p class=note>Average speed per ride. Hollow dots are simulated.</p></div></div>
     <div class=panel><h3 style="margin-top:0">Riding behaviour insights ${BB.badge('estimate')}</h3>${r.insights.map(i => `<div class=al><div class=grow>${esc(i)}</div></div>`).join('')}</div>` } catch (e) { $('an').innerHTML = '<div class="panel empty">Could not load analytics.</div>' } }
document.querySelectorAll('#per button').forEach(b => b.onclick = () => { days = +b.dataset.d; document.querySelectorAll('#per button').forEach(x => x.classList.toggle('on', x === b)); loadAn() });

/* ---------- history + route detail ---------- */
async function loadHist() {
  try { const rs = await BB.get('/api/rides?limit=30'); $('hist').innerHTML = rs.length ? rs.map(r => `<div class=li data-id=${r.id} style="cursor:pointer"><div class=grow><b>${BB.f.date(r.start)} ${BB.f.time(r.start)}</b>${simTag(r.source)}<small>${BB.f.dur(r.duration_s)} · avg ${r.avg_kmh} · max ${r.max_kmh} km/h · ${r.harsh_brake + r.harsh_accel} harsh events</small></div><div style="text-align:right"><b style="font:800 18px Orbitron">${BB.f.km(r.dist_km)}<em style="font:600 11px Rajdhani"> km</em></b><small>${r.eco != null ? 'eco ' + r.eco : ''}</small></div></div>`).join('') : '<div class=empty>No rides yet.</div>';
    $('hist').querySelectorAll('.li').forEach(e => e.onclick = () => detail(e.dataset.id)) } catch (e) {} }
function routeSvg(route, events) { if (!route || route.length < 2) return '<div class=empty>No route recorded.</div>'; const la = route.map(p => p[0]), lo = route.map(p => p[1]), c = Math.cos(la[0] * Math.PI / 180), W = 520, H = 300, pd = 18;
  const x0 = Math.min(...lo), x1 = Math.max(...lo), y0 = Math.min(...la), y1 = Math.max(...la), sc = Math.min((W - pd * 2) / Math.max((x1 - x0) * c, 1e-6), (H - pd * 2) / Math.max(y1 - y0, 1e-6));
  const P = (a, o) => [pd + ((o - x0) * c) * sc + ((W - pd * 2) - (x1 - x0) * c * sc) / 2, H - pd - (a - y0) * sc - ((H - pd * 2) - (y1 - y0) * sc) / 2];
  const pts = route.map(p => P(p[0], p[1]).map(v => v.toFixed(1)).join(',')).join(' '), s = P(route[0][0], route[0][1]), e = P(route[route.length - 1][0], route[route.length - 1][1]);
  return `<svg class=chart viewBox="0 0 ${W} ${H}" style="background:#05101a;border-radius:12px"><polyline points="${pts}" fill=none stroke="var(--c)" stroke-width=3 stroke-linejoin=round stroke-linecap=round />
   ${(events || []).map(v => { const q = P(v.lat, v.lon); return `<circle cx=${q[0]} cy=${q[1]} r=6 fill="${v.type === 'harsh_brake' ? 'var(--r)' : 'var(--y)'}"><title>${v.type === 'harsh_brake' ? 'Sudden braking' : 'Hard acceleration'}: ${v.v0} → ${v.v1} km/h</title></circle>` }).join('')}
   <circle cx=${s[0]} cy=${s[1]} r=7 fill="var(--g)" /><circle cx=${e[0]} cy=${e[1]} r=7 fill="var(--o)" /></svg>` }
async function detail(id) { try { const r = await BB.get('/api/ride/' + id);
  BB.modal(`<h2>${BB.f.date(r.start)} ${BB.f.time(r.start)} ${simTag(r.source)}</h2>${routeSvg(r.route, r.events)}<p class=note><span style="color:var(--g)">●</span> start <span style="color:var(--o)">●</span> end <span style="color:var(--r)">●</span> sudden braking <span style="color:var(--y)">●</span> hard acceleration. Drawn from GPS points, no map tiles needed.</p>
   <div class=stat-big style="margin:10px 0"><div><b>${BB.f.km(r.dist_km)}</b><small>KM</small></div><div><b>${r.avg_kmh}</b><small>AVG</small></div><div><b>${r.max_kmh}</b><small>MAX</small></div></div>
   <p>${BB.f.dur(r.duration_s)} · moving ${BB.f.dur(r.moving_s)} · ${r.harsh_brake} brakes · ${r.harsh_accel} accels · ${r.over_pct}% over limit${r.eco != null ? ` · eco ${r.eco} ${BB.badge('estimate')}` : ''}</p>
   <div class=row><button class="btn dng" id=rdl>Delete</button><button class="btn grow" onclick="BB.close()">Close</button></div>`, m => m.querySelector('#rdl').onclick = () => BB.confirm('Delete this ride?', async () => { try { await BB.del('/api/ride/' + id); loadHist(); loadAn() } catch (e) { BB.err(e) } })) } catch (e) { BB.err(e) } }

BB.tabs.ride = () => { loadHist(); loadAn() }; BB.on('data', () => BB.S.tab === 'ride' && BB.tabs.ride()); BB.on('online', () => BB.S.tab === 'ride' && BB.tabs.ride());
})();
