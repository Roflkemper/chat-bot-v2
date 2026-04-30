'use strict';

const STATE_URL = './STATE/dashboard_state.json';
const RELOAD_INTERVAL_MS = 60000;

let _lastSuccessTs = null;

function fmt(v, d = 2) {
  return v != null ? Number(v).toFixed(d) : 'N/A';
}
function fmtK(v) {
  return v != null ? '$' + Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) : 'N/A';
}
function fmtPct(v) {
  return v != null ? Number(v).toFixed(1) + '%' : 'N/A';
}
function ageStr(tsStr) {
  if (!tsStr) return '—';
  const mins = Math.round((Date.now() - new Date(tsStr).getTime()) / 60000);
  if (mins < 1) return '<1 мин назад';
  if (mins < 60) return `${mins} мин назад`;
  return `${Math.floor(mins / 60)}ч ${mins % 60}м назад`;
}
function el(id) { return document.getElementById(id); }
function set(id, html) { const e = el(id); if (e) e.innerHTML = html; }
function setText(id, text) { const e = el(id); if (e) e.textContent = text; }
function progressBar(pct, cls = '') {
  const w = Math.min(100, Math.max(0, pct || 0));
  return `<div class="bar-wrap"><div class="bar-fill ${cls}" style="width:${w}%"></div></div>`;
}

// ── Section renderers ─────────────────────────────────────────────────────────

function renderHeader(S) {
  const age = S.last_updated_at
    ? Math.round((Date.now() - new Date(S.last_updated_at).getTime()) / 60000)
    : 999;
  const dot = el('freshness-dot');
  if (dot) dot.className = 'dot ' + (age < 6 ? 'green' : age < 20 ? 'yellow' : 'red');
  setText('header-ts', `Обновлено: ${ageStr(S.last_updated_at)}`);
  const price = S.current_price_btc != null
    ? '$' + Number(S.current_price_btc).toLocaleString('ru-RU', { maximumFractionDigits: 0 })
    : '—';
  setText('btc-price', price);
}

function renderPositions(pos) {
  if (!pos) return;
  const shorts = pos.shorts || {};
  const longs = pos.longs || {};
  const shortUnreal = shorts.unrealized_usd || 0;
  const longUnreal = longs.unrealized_usd || 0;
  const shortCls = shortUnreal >= 0 ? 'green' : 'red';
  const longCls = longUnreal >= 0 ? 'green' : 'red';
  set('pos-shorts', `
    <div class="stat-label">Шорты</div>
    <div class="stat-value">${fmt(shorts.total_btc, 4)} BTC</div>
    <div class="${shortCls}" style="font-size:12px">${shortUnreal >= 0 ? '+' : ''}${fmt(shortUnreal, 0)} USD нереализ.</div>`);
  set('pos-longs', `
    <div class="stat-label">Лонги</div>
    <div class="stat-value">${fmtK(longs.total_usd)}</div>
    <div class="${longCls}" style="font-size:12px">${longUnreal >= 0 ? '+' : ''}${fmt(longUnreal, 0)} USD нереализ.</div>`);
  const fm = pos.free_margin_pct;
  const fmPct = fm != null ? Math.round(fm) : 0;
  const fmCls = fmPct > 50 ? '' : fmPct > 20 ? 'warn' : 'danger';
  const dd = pos.drawdown_pct || 0;
  set('pos-margin', `
    <div class="stat-label">Свободная маржа</div>
    <div class="stat-value">${fmPct}%</div>
    ${progressBar(fmPct, fmCls)}
    <div class="bar-label"><span>0%</span><span>100%</span></div>
    <div style="margin-top:6px;font-size:12px" class="${dd > 5 ? 'red' : 'muted'}">Просадка: ${fmtPct(dd)}</div>`);
}

function renderCompetition(comp) {
  if (!comp) return;
  const rank = comp.rank != null ? `🥇`.replace('1', '') + `#${comp.rank}` : '—';
  const volTotal = comp.volume_total_usd || 0;
  const volTarget = comp.volume_target_usd || 10500000;
  const volPct = volTarget > 0 ? (volTotal / volTarget * 100) : 0;
  const volCls = volPct > 70 ? '' : volPct > 40 ? 'warn' : 'danger';
  const daysRem = comp.days_remaining != null ? comp.days_remaining : '—';
  const dailyAvg = comp.daily_volume_avg != null ? fmtK(comp.daily_volume_avg) : '—';
  const proj = comp.projected_volume_30d != null ? fmtK(comp.projected_volume_30d) : '—';
  const rebate = comp.rebate_estimate || '—';
  set('competition-card', `
    <div class="grid3">
      <div>
        <div class="stat-label">Место</div>
        <div class="stat-value blue">${comp.rank != null ? '#' + comp.rank : '—'}</div>
      </div>
      <div>
        <div class="stat-label">PnL конкурс</div>
        <div class="stat-value green">${fmtK(comp.pnl_total_usd)}</div>
      </div>
      <div>
        <div class="stat-label">Дней осталось</div>
        <div class="stat-value">${daysRem}</div>
      </div>
    </div>
    <div style="margin-top:10px">
      <div class="stat-label">Объём: ${fmtK(volTotal)} / ${fmtK(volTarget)}</div>
      ${progressBar(volPct, volCls)}
      <div class="bar-label"><span>${volPct.toFixed(1)}%</span><span>цель</span></div>
    </div>
    <div class="grid2" style="margin-top:10px">
      <div><span class="muted">Темп: </span>${dailyAvg}/день</div>
      <div><span class="muted">Прогноз 30d: </span>${proj}</div>
    </div>
    <div style="margin-top:6px;font-size:12px"><span class="muted">Прогноз ребейта: </span><span class="green">${rebate}</span></div>`);
}

function renderPhase1(pj) {
  if (!pj) return;
  const dayN = pj.day_n || 0;
  const dayTotal = pj.day_total || 14;
  const pct = dayTotal > 0 ? dayN / dayTotal * 100 : 0;
  const regimes = pj.regime_distribution || {};
  const regStr = Object.entries(regimes)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k} ${Math.round(v * 100)}%`)
    .join(', ') || '—';
  set('phase1-card', `
    <div class="grid2">
      <div>
        <div class="stat-label">День</div>
        <div class="stat-value">${dayN} / ${dayTotal}</div>
        ${progressBar(pct)}
        <div class="bar-label"><span>Day ${dayN}</span><span>${dayTotal}</span></div>
      </div>
      <div>
        <div class="stat-label">Сигналов / Null</div>
        <div class="stat-value">${pj.advise_signals_count} / <span class="muted">${pj.null_signals_count}</span></div>
        <div style="margin-top:6px;font-size:12px"><span class="muted">Сетап: </span><span class="yellow">${pj.dominant_setup || '—'}</span></div>
      </div>
    </div>
    <div style="margin-top:8px;font-size:12px"><span class="muted">Режимы: </span>${regStr}</div>`);
}

function renderEngine(eng) {
  if (!eng) return;
  const bugsFixed = eng.bugs_fixed || 0;
  const bugsTotal = eng.bugs_detected || 0;
  const allFixed = bugsTotal > 0 && bugsFixed >= bugsTotal;
  const calDate = eng.calibration_done_at
    ? new Date(eng.calibration_done_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
    : '—';
  set('engine-card', `
    <div class="grid2">
      <div>
        <div class="stat-label">Калибровка</div>
        <div style="font-size:12px;margin-top:2px">${calDate}</div>
      </div>
      <div>
        <div class="stat-label">Багов</div>
        <div class="stat-value ${allFixed ? 'green' : 'red'}">${bugsFixed}/${bugsTotal}</div>
      </div>
    </div>
    ${!allFixed ? `<div class="engine-bug">⚠ ${bugsTotal - bugsFixed} бага(ов) ожидают исправления — ${eng.fix_eta || 'pending'}</div>` : ''}`);
}

function renderBoli(boli) {
  if (!boli || !boli.length) return;
  const rows = boli.map(b => {
    const sc = b.status === 'done' ? 'status-done' : b.status === 'in_progress' ? 'status-in_progress' : 'status-manual';
    const label = b.status === 'done' ? 'готово' : b.status === 'in_progress' ? 'в работе' : 'ручной';
    const icon = b.status === 'done' ? '🟢' : b.status === 'in_progress' ? '🟡' : '🔴';
    return `<div class="boli-row">
      <span class="boli-id">#${b.id}</span>
      <span style="flex:1">${icon} ${b.name}</span>
      <span class="status-badge ${sc}">${label}</span>
    </div>`;
  }).join('');
  set('boli-card', rows);
}

function renderDecisions(decisions) {
  if (!decisions) return;
  if (!decisions.length) { set('decisions-card', '<span class="muted">Нет событий</span>'); return; }
  const rows = decisions.map(d => {
    const ts = d.ts ? new Date(d.ts).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '—';
    const outCls = d.outcome === 'pending' ? 'muted' : 'green';
    return `<tr>
      <td class="muted" style="font-size:11px">${ts}</td>
      <td>${d.type || '—'}</td>
      <td class="muted" style="font-size:11px">${d.event_id || ''}</td>
      <td class="${outCls}">${d.outcome || '—'}</td>
    </tr>`;
  }).join('');
  set('decisions-card', `<table>
    <thead><tr><th>время</th><th>тип</th><th>id</th><th>итог</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`);
}

function renderClusters(clusters) {
  if (!clusters) return;
  if (!clusters.length) { set('clusters-card', '<span class="muted">Нет активных кластеров — добавь через /liq_set</span>'); return; }
  const rows = clusters.map(c => {
    const dir = c.direction === 'above' ? '⬆' : '⬇';
    const dirCls = c.direction === 'above' ? 'red' : 'green';
    const age = c.age_hours != null ? `${c.age_hours}ч назад` : '';
    return `<div class="cluster-row">
      <span class="cluster-dir ${dirCls}">${dir}</span>
      <span>${fmtK(c.price)}</span>
      <span class="muted">${c.label || ''}</span>
      <span class="muted" style="margin-left:auto;font-size:11px">${age}</span>
    </div>`;
  }).join('');
  set('clusters-card', rows);
}

function renderAlerts(alerts) {
  if (!alerts) return;
  if (!alerts.length) { set('alerts-card', '<span class="muted">✅ Нет оповещений за 24ч</span>'); return; }
  const rows = alerts.slice().reverse().map(a => {
    const ts = a.ts ? new Date(a.ts).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
    return `<div class="alert-row"><span class="alert-ts">${ts}</span>${a.msg || ''}</div>`;
  }).join('');
  set('alerts-card', rows);
}

// ── Main render ───────────────────────────────────────────────────────────────

function renderAll(S) {
  renderHeader(S);
  renderPositions(S.positions);
  renderCompetition(S.competition);
  renderPhase1(S.phase_1_paper_journal);
  renderEngine(S.engine_status);
  renderBoli(S.boli_status);
  renderDecisions(S.recent_decisions);
  renderClusters(S.active_liq_clusters);
  renderAlerts(S.alerts_24h);
  _lastSuccessTs = S.last_updated_at;
  const banner = el('offline-banner');
  if (banner) banner.style.display = 'none';
}

// ── Fetch & reload ────────────────────────────────────────────────────────────

async function fetchState() {
  try {
    const resp = await fetch(STATE_URL + '?t=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const S = await resp.json();
    renderAll(S);
  } catch (e) {
    const banner = el('offline-banner');
    if (banner) {
      const lastStr = _lastSuccessTs
        ? ` Последние данные: ${ageStr(_lastSuccessTs)}.`
        : '';
      banner.innerHTML = `⚠ Dashboard offline — не удалось загрузить данные.${lastStr}<br>
        Запустите <code>python -m http.server 8000</code> в папке <code>C:\\bot7\\docs\\</code>`;
      banner.style.display = 'block';
    }
  }
}

fetchState();
setInterval(fetchState, RELOAD_INTERVAL_MS);
