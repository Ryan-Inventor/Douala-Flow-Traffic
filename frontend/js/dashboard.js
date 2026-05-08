/**
 * ==============================================================================
 * DOUALAFLOW — dashboard.js (Refonte UI + Fixes Temps Réel)
 * ==============================================================================
 *
 * CORRECTIONS :
 * - Intervalles plus courts pour une vraie animation temps réel
 * - Indicateur "Dernière mise à jour" visible
 * - Couleurs et classes adaptées au nouveau CSS
 * - getStatus/getColor cohérents avec le backend corrigé
 * ==============================================================================
 */

const API_BASE = 'http://localhost:5000/api';

const INTERVALS = {
  current:  3000,   // 3s — état trafic (était 5s)
  vehicles: 2000,   // 2s — animation véhicules
  stats:    3000,   // 3s — KPIs header
};

// Couleurs par axe pour le graphique
const CHART_COLORS = {
  ndokoti:   '#ff3b30',
  bonaberi:  '#34c759',
  bassa:     '#ff9500',
  akwa:      '#ffcc00',
  makepe:    '#5ac8fa',
  logbessou: '#bf5af2',
};

const getColor  = (c) => c > 70 ? '#ff3b30' : c > 55 ? '#ff9500' : c > 40 ? '#ffcc00' : '#34c759';
const getStatus = (c) => c > 70 ? 'saturé'  : c > 40 ? 'ralenti' : 'fluide';

// ==============================================================================
// ÉTAT
// ==============================================================================
const State = {
  current:     null,
  predictions: null,
  chart:       null,
  filter:      'tous',
  predHorizon: '+1h',
  intervals:   [],
  ready:       false,
};

// ==============================================================================
// API
// ==============================================================================
async function api(endpoint) {
  try {
    const r = await fetch(`${API_BASE}${endpoint}`);
    if (!r.ok) {
      if (r.status === 503) console.error('[DoualaFlow] Données non générées — lancez generate_data.py + process_bigdata.py');
      else console.error(`[DoualaFlow] Erreur ${endpoint}: HTTP ${r.status}`);
      return null;
    }
    return await r.json();
  } catch {
    return null;
  }
}

// ==============================================================================
// HORLOGE
// ==============================================================================
function startClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  const tick = () => el.textContent = new Date().toLocaleTimeString('fr-FR');
  tick();
  setInterval(tick, 1000);
}

// ==============================================================================
// MISE À JOUR DU HEADER
// ==============================================================================
async function refreshStats() {
  const data = await api('/stats');
  if (!data) return;

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  const congColor = getColor(data.avg_congestion);
  set('hdr-congestion', `${data.avg_congestion}%`);
  const congEl = document.getElementById('hdr-congestion');
  if (congEl) congEl.style.color = congColor;

  const dot = document.getElementById('hdr-cong-dot');
  if (dot) dot.style.background = congColor;

  set('hdr-speed', `${data.avg_speed_kmh} km/h`);
  if (data.most_congested) set('hdr-worst', data.most_congested.label);
  if (data.most_fluid)     set('hdr-best',  data.most_fluid.label);

  // Alerte
  const strip = document.getElementById('alert-strip');
  const alertTxt = document.getElementById('alert-text');
  if (strip && alertTxt) {
    if (data.alert) {
      alertTxt.textContent = data.alert;
      strip.classList.add('visible');
    } else {
      strip.classList.remove('visible');
    }
  }
}

// ==============================================================================
// KPIs SIDEBAR
// ==============================================================================
function updateKPIs(current, stats) {
  if (!current || !stats) return;

  const axes = current.axes ?? {};
  const congs = Object.values(axes).map(a => a.congestion);
  const maxC  = Math.max(...congs);

  const set = (id, val, col) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = val;
    if (col) el.style.color = col;
  };

  set('kpi-max-cong',    `${maxC.toFixed(0)}%`, getColor(maxC));
  set('kpi-avg-speed',   `${stats.avg_speed_kmh}`);
  set('kpi-max-delta',   maxC > 70 ? '⚠ saturé' : maxC > 40 ? 'ralenti' : 'fluide');
  set('kpi-speed-badge', stats.avg_speed_kmh > 30 ? '→ normal' : '↓ lent');
}

// ==============================================================================
// LISTE DES AXES
// ==============================================================================
function renderAxes(axesData) {
  const container = document.getElementById('axes-list');
  if (!container || !axesData) return;

  const sorted = Object.entries(axesData).sort(([,a],[,b]) => b.congestion - a.congestion);

  const filtered = sorted.filter(([, d]) => {
    if (State.filter === 'tous')   return true;
    if (State.filter === 'SATURÉ') return d.status === 'SATURÉ';
    if (State.filter === 'FLUIDE') return d.status === 'FLUIDE';
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:18px;color:var(--text-secondary);font-size:11px;">Aucun axe avec ce statut.</div>`;
    return;
  }

  container.innerHTML = filtered.map(([name, d], i) => {
    const col    = getColor(d.congestion);
    const stCls  = getStatus(d.congestion);

    return `
      <div class="axis-item" onclick="DoualaFlow.focusAxis('${name}')" style="animation-delay:${i*40}ms">
        <div class="axis-item-top">
          <div class="axis-name">
            <div class="axis-dot" style="background:${col}"></div>
            <span style="color:${col}">${d.label}</span>
          </div>
          <div class="status-tag ${stCls}">${d.status}</div>
        </div>
        <div class="axis-zone-txt">${d.zone ?? ''}</div>
        <div class="congestion-track">
          <div class="progress-bg">
            <div class="progress-fill" style="width:${d.congestion.toFixed(1)}%;background:${col}"></div>
          </div>
          <div class="congestion-pct">${d.congestion.toFixed(0)}%</div>
        </div>
        <div class="axis-meta">🚗 ${d.speed_kmh.toFixed(1)} km/h &nbsp;·&nbsp; ${d.vehicle_count ?? '—'} véhicules</div>
      </div>`;
  }).join('');
}

// ==============================================================================
// PRÉDICTIONS ML
// ==============================================================================
function renderPredictions(horizon) {
  const data      = State.predictions;
  const container = document.getElementById('predictions-content');
  if (!data || !container) return;

  const hData = data.horizons?.[horizon];
  if (!hData) {
    container.innerHTML = `<div style="font-size:11px;color:var(--text-secondary);padding:8px;">Non disponible.</div>`;
    return;
  }

  const axes = Object.entries(hData.axes ?? {}).sort(([,a],[,b]) => b.congestion - a.congestion);

  container.innerHTML = axes.map(([, ax]) => `
    <div class="pred-row">
      <span class="pred-axis">${ax.label}</span>
      <div style="display:flex;align-items:center;gap:6px;">
        <div class="pred-minibar">
          <div class="pred-minibar-fill" style="width:${ax.congestion}%;background:${ax.color}"></div>
        </div>
        <span class="pred-val" style="color:${ax.color}">${ax.congestion.toFixed(0)}%</span>
      </div>
    </div>`).join('');
}

// ==============================================================================
// GRAPHIQUE CHART.JS
// ==============================================================================
function initChart(chartData) {
  const canvas = document.getElementById('chart-canvas');
  if (!canvas || !chartData) return;

  const ctx      = canvas.getContext('2d');
  const curHour  = new Date().getHours();

  const datasets = Object.entries(chartData.datasets ?? {}).map(([name, ds]) => ({
    label:           ds.label,
    data:            ds.congestion,
    borderColor:     CHART_COLORS[name] ?? '#8e8e93',
    backgroundColor: (CHART_COLORS[name] ?? '#8e8e93') + '12',
    borderWidth:     1.5,
    pointRadius:     0,
    pointHoverRadius: 3,
    tension:         0.4,
    fill:            false,
  }));

  State.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels:   chartData.labels.map(h => `${String(h).padStart(2,'0')}h`),
      datasets,
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:         { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15,17,23,0.96)',
          borderColor:     'rgba(255,255,255,0.08)',
          borderWidth:     1,
          titleColor:      '#f5f5f7',
          bodyColor:       '#8e8e93',
          padding:         10,
          callbacks: {
            title:  ([i]) => `Heure : ${i.label}`,
            label:  (i)   => ` ${i.dataset.label} : ${i.raw.toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          grid:  { color: 'rgba(255,255,255,0.04)', drawTicks: false },
          ticks: {
            color:    '#48484a',
            font:     { family: 'JetBrains Mono, monospace', size: 9 },
            maxRotation: 0,
            callback: (v, i) => [0,6,9,12,15,17,18,21].includes(i) ? `${String(i).padStart(2,'0')}h` : '',
          },
        },
        y: {
          min: 0, max: 100,
          grid:  { color: 'rgba(255,255,255,0.04)', drawTicks: false },
          ticks: {
            color:    '#48484a',
            font:     { family: 'JetBrains Mono, monospace', size: 9 },
            callback: v => `${v}%`,
            stepSize: 25,
          },
        },
      },
      animation: { duration: 600, easing: 'easeInOutQuart' },
    },
  });

  // Plugin ligne verticale "maintenant"
  Chart.register({
    id: 'currentHourLine',
    afterDraw(chart) {
      const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
      if (!x) return;
      const xPos = x.getPixelForValue(curHour);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(xPos, top);
      ctx.lineTo(xPos, bottom);
      ctx.strokeStyle = 'rgba(0,122,255,0.5)';
      ctx.lineWidth   = 1;
      ctx.setLineDash([4,3]);
      ctx.stroke();
      ctx.fillStyle = 'rgba(0,122,255,0.8)';
      ctx.font      = 'bold 8px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('MAINTENANT', xPos, top - 2);
      ctx.restore();
    },
  });

  State.chart.update('none');

  // Légende custom
  const legendEl = document.getElementById('chart-legend');
  if (legendEl) {
    legendEl.innerHTML = Object.entries(chartData.datasets ?? {}).map(([name, ds]) => `
      <div class="legend-item" onclick="DoualaFlow.toggleChart('${name}', this)">
        <div class="legend-dot" style="background:${CHART_COLORS[name] ?? '#8e8e93'}"></div>
        <span>${ds.label}</span>
      </div>`).join('');
  }
}

// ==============================================================================
// RAFRAÎCHISSEMENT PRINCIPAL
// ==============================================================================
async function refreshCurrent() {
  const [current, stats] = await Promise.all([api('/current'), api('/stats')]);
  if (!current) return;

  State.current = current;
  DoualaMape.updateAxes(current);
  renderAxes(current.axes);
  updateKPIs(current, stats);

  // Indicateur dernière mise à jour
  const el = document.getElementById('last-update');
  if (el) el.textContent = new Date().toLocaleTimeString('fr-FR');
}

async function refreshVehicles() {
  const data = await api('/vehicles');
  if (!data?.vehicles) return;

  DoualaMape.updateVehicles(data.vehicles);

  const el = document.getElementById('kpi-vehicles');
  if (el) el.textContent = data.count;
}

// ==============================================================================
// MODULE PUBLIC
// ==============================================================================
const DoualaFlow = {

  async init() {
    if (State.ready) return;
    State.ready = true;

    console.log('[DoualaFlow] Démarrage...');
    startClock();

    // Charger graphique + prédictions (données statiques)
    const [chartData, predsData] = await Promise.all([api('/chart'), api('/predictions')]);
    State.predictions = predsData;

    if (chartData) initChart(chartData);
    if (predsData) renderPredictions(State.predHorizon);

    // Premier chargement trafic
    await Promise.all([refreshCurrent(), refreshStats()]);
    await refreshVehicles();

    // Boucles de rafraîchissement
    State.intervals.push(
      setInterval(refreshCurrent,  INTERVALS.current),
      setInterval(refreshVehicles, INTERVALS.vehicles),
      setInterval(refreshStats,    INTERVALS.stats),
    );

    console.log('[DoualaFlow] Prêt ✓');
  },

  filterAxes(el, filter) {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    State.filter = filter;
    if (State.current) renderAxes(State.current.axes);
  },

  showPredHorizon(el, horizon) {
    document.querySelectorAll('.pred-chip').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    State.predHorizon = horizon;
    renderPredictions(horizon);
  },

  focusAxis(name) {
    DoualaMape.focusAxis(name);
  },

  toggleChart(name, el) {
    if (!State.chart) return;
    const order = ['ndokoti','bonaberi','bassa','akwa','makepe','logbessou'];
    const idx   = order.indexOf(name);
    if (idx < 0) return;
    const meta    = State.chart.getDatasetMeta(idx);
    meta.hidden   = !meta.hidden;
    State.chart.update();
    el.style.opacity = meta.hidden ? '0.3' : '1';
  },
};

// Démarrage auto
document.addEventListener('DOMContentLoaded', () => DoualaFlow.init());
