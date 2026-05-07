'use strict';

// app_runner.dashboard_http serves /state.json directly. Was './STATE/dashboard_state.json'
// которое 404 на http://127.0.0.1:8765/ — фикс 2026-05-07.
const STATE_URL = '/state.json';
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

// ── Freshness banner (TZ-DASHBOARD-LIVE-FRESHNESS) ──────────────────────────

function renderFreshness(F) {
  if (!F) return;
  const banner = el('freshness-banner');
  if (!banner) return;
  const lvl = F.level || 'ok';
  if (lvl === 'ok' && (!F.notes || F.notes.length === 0)) {
    banner.style.display = 'none';
    return;
  }
  const colors = { ok: 'var(--green)', yellow: 'var(--yellow)', red: 'var(--red)' };
  const icons = { ok: 'OK', yellow: '⚠', red: '🔴' };
  const ages = F.ages_min || {};
  const ageLines = [];
  if (ages.snapshots_min != null) ageLines.push(`позиции ${ages.snapshots_min} мин`);
  if (ages.latest_forecast_min != null) ageLines.push(`прогноз ${ages.latest_forecast_min} мин`);
  if (ages.regime_state_min != null) ageLines.push(`регим ${ages.regime_state_min} мин`);
  banner.innerHTML = `
    <div style="background: ${colors[lvl]}; padding: 8px; border-radius: 4px; margin-bottom: 12px; font-size: 12px;">
      <strong>${icons[lvl]} Свежесть данных:</strong> ${ageLines.join(' • ')}<br>
      ${(F.notes || []).map(n => `• ${n}`).join('<br>')}
      <div style="font-size: 10px; opacity: 0.7; margin-top: 4px">${F.data_source || F.exchange_api_status || ''}</div>
    </div>
  `;
  banner.style.display = 'block';
}

// ── Regime / Forecast / Virtual trader (P4 wire-in 2026-05-05) ───────────────

function renderRegime(R) {
  if (!R || !R.label) {
    set('regime-card', `<span class="muted">${R?.note || 'Нет данных о режиме.'}</span>`);
    return;
  }
  const conf = R.confidence != null ? Number(R.confidence).toFixed(2) : '—';
  const stab = R.stability  != null ? Number(R.stability).toFixed(2)  : '—';
  const stableBars = R.stable_bars != null ? R.stable_bars : '—';
  const switchInfo = R.switch_pending
    ? `<span class="yellow">кандидат: ${R.candidate_regime} (${R.candidate_bars} баров)</span>`
    : '<span class="green">смены не ожидается</span>';
  const updated = R.last_updated ? ageStr(R.last_updated) : '—';
  set('regime-card', `
    <div class="grid3">
      <div>
        <div class="stat-label">Текущий режим</div>
        <div class="stat-value">${R.label}</div>
        <div class="muted" style="font-size:11px">обновлено ${updated}</div>
      </div>
      <div>
        <div class="stat-label">Уверенность / Стабильность</div>
        <div class="stat-value">${conf} / ${stab}</div>
        <div class="muted" style="font-size:11px">стабильно ${stableBars} баров</div>
      </div>
      <div>
        <div class="stat-label">Авто-переключение</div>
        <div style="font-size:13px;margin-top:4px">${switchInfo}</div>
      </div>
    </div>
  `);
}

function bandClass(band) {
  if (band === 'green') return 'green';
  if (band === 'yellow') return 'yellow';
  if (band === 'red') return 'red';
  return 'muted';
}

// Forecast renderer retired (TZ-FORECAST-DECOMMISSION). Replaced with a
// neutral notice card. See FORECAST_CALIBRATION_DIAGNOSTIC_v1.md for the
// verdict (FUNDAMENTALLY WEAK; resolution = 0.0001; calibrated Brier
// recovers no-skill 0.2500 baseline only).
function renderForecastRetiredNotice() {
  set('forecast-card', `
    <div class="muted" style="font-size:12px">
      Прогнозный блок выведен из эксплуатации (TZ-FORECAST-DECOMMISSION).<br>
      <span style="font-size:11px">Основание:
        <a href="RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md">FORECAST_CALIBRATION_DIAGNOSTIC v1</a>
        — модель не имеет resolution-skill (Brier ≈ 0.2500 после калибровки = 50/50 baseline).
      </span><br>
      <span style="font-size:11px">Регламент v0.1.1+ опирается только на регим-классификатор;
        решения по активации ботов см. карточку «Регламент» выше.</span>
    </div>
  `);
}

function renderRegulationCard(R) {
  // P1: render the operator-facing regulation action card.
  if (!R) {
    set('regulation-card', '<span class="muted">Нет данных регламента.</span>');
    return;
  }
  if (R.note && (!R.on || R.on.length === 0) && (!R.conditional || R.conditional.length === 0)) {
    set('regulation-card', `<span class="muted">${R.note}</span>`);
    return;
  }
  const renderSection = (title, rows, cls) => {
    if (!rows || rows.length === 0) return '';
    const items = rows.map(r =>
      `<li><span class="${cls}" style="font-weight:bold">${r.cfg_id}</span><br>
        <span class="muted" style="font-size:11px">${r.reason}</span></li>`
    ).join('');
    return `<div style="margin-top:8px"><div class="stat-label">${title}</div><ul style="margin:4px 0 0 16px;padding:0;list-style:disc">${items}</ul></div>`;
  };
  const noRule = R.no_rule || [];
  set('regulation-card', `
    <div class="muted" style="font-size:11px;margin-bottom:6px">
      Регламент ${R.regulation_version || '—'} • режим <strong>${R.regime_label || '—'}</strong>
      ${R.note ? `<br>${R.note}` : ''}
    </div>
    ${renderSection('ON (разрешено)', R.on, 'green')}
    ${renderSection('CONDITIONAL (с мониторингом)', R.conditional, 'yellow')}
    ${renderSection('OFF (запрещено)', R.off, 'red')}
    ${renderSection('NO RULE (вне регламента)', noRule, 'muted')}
  `);
}

function renderVirtualTrader(V) {
  if (!V) {
    set('virtual-trader-card', '<span class="muted">Нет данных.</span>');
    return;
  }
  const decided = V.wins + V.losses;
  const wrLabel = V.win_rate_pct != null ? `${V.win_rate_pct}%` : '—';
  const wrCls = V.win_rate_pct != null && V.win_rate_pct >= 50 ? 'green' : (V.win_rate_pct != null ? 'red' : 'muted');
  const rrCls = V.avg_rr > 0 ? 'green' : (V.avg_rr < 0 ? 'red' : 'muted');
  const openRows = (V.open_positions || []).map(p => {
    const dir = p.direction === 'short' ? 'Шорт' : 'Лонг';
    const dirCls = p.direction === 'short' ? 'red' : 'green';
    const half = p.half_closed ? ' <span class="yellow">[TP1]</span>' : '';
    return `
      <tr>
        <td><span class="${dirCls}">${dir}</span>${half}</td>
        <td>${fmt(p.entry_price, 0)}</td>
        <td>${ageStr(p.entry_time)}</td>
        <td>SL ${fmt(p.sl, 0)} / TP1 ${fmt(p.tp1, 0)} / TP2 ${fmt(p.tp2, 0)}</td>
      </tr>
    `;
  }).join('');
  const openTable = openRows
    ? `<table style="margin-top:8px"><thead><tr><th>Направ.</th><th>Вход</th><th>Открыто</th><th>SL/TP1/TP2</th></tr></thead><tbody>${openRows}</tbody></table>`
    : '<div class="muted" style="margin-top:6px;font-size:11px">Открытых виртуальных позиций нет.</div>';
  set('virtual-trader-card', `
    <div class="grid3">
      <div>
        <div class="stat-label">Сигналов / Win / Loss / Open</div>
        <div class="stat-value">${V.signals_7d} / ${V.wins} / ${V.losses} / ${V.open}</div>
      </div>
      <div>
        <div class="stat-label">Win-rate (по решённым ${decided})</div>
        <div class="stat-value ${wrCls}">${wrLabel}</div>
      </div>
      <div>
        <div class="stat-label">Средний R:R</div>
        <div class="stat-value ${rrCls}">${V.avg_rr != null ? V.avg_rr.toFixed(2) : '—'}</div>
      </div>
    </div>
    ${openTable}
    <div class="muted" style="font-size:11px;margin-top:8px">
      Тренд для отладки модели, не торговый совет.
    </div>
  `);
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
  renderFreshness(S.freshness);
  renderRegime(S.regime);
  renderRegulationCard(S.regulation_action_card);
  renderForecastRetiredNotice();
  renderVirtualTrader(S.virtual_trader);
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
        Проверьте что app_runner запущен (supervisor) и dashboard_http_task живой.`;
      banner.style.display = 'block';
    }
  }
}

fetchState();
setInterval(fetchState, RELOAD_INTERVAL_MS);
