/* Service tab: predictive maintenance (reminders by distance AND time, riding-pace projection), suggestions, battery health trend,
   maintenance history, and the fault / abnormality log. Everything shows its basis: user-entered, estimate, sensor, simulated. */
(() => {
const V = $('v-service'), STATUS = {ok: 'On track', soon: 'Due soon', overdue: 'Overdue'};
V.innerHTML = `<div class=row style="margin-bottom:10px"><h2 class=grow style="margin:0">Maintenance</h2><button class="btn sm pri" id=lgs>+ Log service</button></div><div id=sm></div>`;
const today = () => new Date().toISOString().slice(0, 10);
BB.garage = {logService() { const o = (BB.S.status && BB.S.status.state.odometer) || '';
  BB.form('Log service or repair', [{k: 'date', label: 'Date', type: 'date', val: today(), req: 1}, {k: 'type', label: 'Type', type: 'select', opts: ['service', 'oil', 'chain', 'brake', 'tyre', 'battery', 'repair', 'other'], val: 'service'},
    {k: 'odo', label: 'Odometer (km)', type: 'number', val: Math.round(o) || '', ph: 'e.g. 9050'}, {k: 'cost', label: 'Cost (₹)', type: 'number', ph: '0'}, {k: 'shop', label: 'Workshop', ph: 'Optional'}, {k: 'note', label: 'Notes', ph: 'What was done'}],
    async v => { await BB.post('/api/garage/services', v); BB.toast('Saved. Reminders updated.'); BB.emit('data'); BB.poll() }) }};
$('lgs').onclick = BB.garage.logService;

const rem = r => { const km = r.due_km, d = r.due_days;
  const when = [km != null ? (km >= 0 ? `${km} km left` : `${-km} km over`) : '', d != null ? (d >= 0 ? `${d} days left` : `${-d} days over`) : ''].filter(Boolean).join(' · ') || r.note;
  return `<div class=li style="align-items:flex-start"><div class=grow><b>${esc(r.title)}</b> <span class="st ${r.status}">${STATUS[r.status]}</span><small>${esc(when)}${r.due_on && !r.key.startsWith('doc') ? ' · by ' + r.due_on : ''}${r.key.startsWith('doc') ? ' · expires ' + r.due_on : ''}</small>
    ${r.progress != null ? `<div class="bar ${r.status}"><i style="width:${Math.round(r.progress * 100)}%"></i></div>` : ''}${r.projected_days != null ? `<small>At your recent pace: about ${r.projected_days} days ${BB.badge('estimate')}${r.projected_basis === 'simulated' ? ' <span class=sim-tag>based on SIM rides</span>' : ''}</small>` : ''}</div>${BB.badge(r.key.startsWith('doc') || r.key === 'brake' ? 'user' : 'estimate')}</div>` };

async function load() { let d; try { d = await BB.get('/api/maint') } catch (e) { $('sm').innerHTML = '<div class="panel empty">Could not load maintenance data.</div>'; return }
  const b = d.battery, sg = d.suggestions, hist = d.history;
  $('sm').innerHTML = `
  <div class=panel><h2>Reminders</h2><p class=note>Distance from your odometer and last service, time from your last service date. Estimates, not measured wear.</p><div class=list>${d.reminders.map(rem).join('')}</div></div>
  <div class=panel><div class=row><h2 class=grow style="margin:0">Suggestions</h2>${BB.badge(sg.ai ? 'estimate' : 'estimate')}<span class=note>${sg.ai ? 'AI-generated' : 'Rule-based'}</span></div>
   ${sg.items.length ? sg.items.map(i => `<div class="al ${i.priority === 1 ? 'critical' : i.priority === 2 ? 'warn' : 'info'}"><div class=grow><b>${esc(i.basis)}</b>${esc(i.title)}<br><span class=note>${esc(i.why)}</span></div></div>`).join('') : '<div class=ok-line>Nothing urgent. Maintenance looks on track.</div>'}</div>
  <div class=panel><div class=row><h2 class=grow style="margin:0">Battery health</h2>${BB.badge(b.basis === 'sensor' ? 'sensor' : b.basis === 'simulated' ? 'sim' : 'none')}</div>
   ${b.status === 'no_data' ? `<p class=note>${esc(b.message)}</p>` : `<div class=stat-big style="margin:12px 0"><div><b>${b.resting_v} V</b><small>RESTING</small></div><div><b style="font-size:20px">${esc(b.status.toUpperCase())}</b><small>STATE</small></div><div><b style="font-size:20px">${b.trend_v_per_week != null ? (b.trend_v_per_week > 0 ? '+' : '') + b.trend_v_per_week : '--'}</b><small>V / WEEK</small></div></div><p class=note>${esc(b.message)}${b.est_days_to_12v ? ` Estimate: could reach 12.0 V in about ${b.est_days_to_12v} days if the trend continues.` : ''} Based on ${b.samples} readings with the engine off (${b.span_days} days).${b.basis === 'simulated' ? ' <b>These readings are simulated.</b>' : ''}</p>`}</div>
  <div class=panel><h2>Service history</h2><div class=list>${hist.services.length ? hist.services.map(s => `<div class=li><div class=grow><b>${esc(s.type)}</b> · ${esc(s.date)}<small>${s.odo != null ? s.odo + ' km' : ''}${s.cost ? ' · ' + BB.f.rs(s.cost) : ''}${s.shop ? ' · ' + esc(s.shop) : ''}${s.note ? ' · ' + esc(s.note) : ''}</small></div>${BB.badge('user')}<button class="btn sm dng" data-d=${s.id}>✕</button></div>`).join('') : '<div class=empty>No service records yet. Log one to start tracking.</div>'}</div>
   ${hist.voice_notes.length ? `<h3>Voice notes</h3>${hist.voice_notes.map(n => `<div class=note>• ${esc(n.note)}</div>`).join('')}` : ''}</div>
  <div class=panel><h2>Fault &amp; abnormality log</h2><p class=note>Every alert the bike raised, with when it started and when it cleared.</p><div class=list>${d.faults.length ? d.faults.map(f => `<div class=li><div class=grow><span class="st ${f.level === 'critical' ? 'overdue' : f.level === 'warn' ? 'soon' : 'ok'}">${f.level}</span> ${esc(f.text)}<small>${BB.f.date(f.t0)} ${BB.f.time(f.t0)} → ${f.t1 ? BB.f.time(f.t1) + ' (cleared)' : '<b style="color:var(--o)">still active</b>'}</small></div>${BB.badge(f.src)}</div>`).join('') : '<div class=empty>No faults logged.</div>'}</div></div>`;
  $('sm').querySelectorAll('[data-d]').forEach(x => x.onclick = () => BB.confirm('Delete this service record? (Counters are not rolled back.)', async () => { try { await BB.del('/api/garage/services/' + x.dataset.d); load() } catch (e) { BB.err(e) } })) }
BB.tabs.service = load; BB.on('data', () => BB.S.tab === 'service' && load()); BB.on('online', () => BB.S.tab === 'service' && load());
})();
