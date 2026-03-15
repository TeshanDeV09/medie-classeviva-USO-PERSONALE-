/**
 * main.js — ClasseViva Dashboard
 * Medie calcolate client-side direttamente da state.voti (più affidabile).
 */
'use strict';

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  voti: [],
  student: {},
  calcMode: 'arithmetic',
  pesi: { scritto: 50, verifica: 50, orale: 30, pratico: 20, altro: 0 },
  sortCol: 'materia',
  sortDir: 'asc',
  searchQuery: '',
  filterMateria: 'all',
};

let chartLine = null;
let chartBar  = null;

const $ = sel => document.querySelector(sel);
const $$ = sel => [...document.querySelectorAll(sel)];

// ── Utilities ─────────────────────────────────────────────────────────────
function debounce(fn, ms = 300) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function throttle(fn, ms = 1000) {
  let last = 0;
  return (...a) => { const now = Date.now(); if (now - last >= ms) { last = now; fn(...a); } };
}
function gradeClass(v) {
  if (v === null || v === undefined) return '';
  if (v > 8.25)  return 'grade-top';   // sopra 8+ -> blu
  if (v >= 6)    return 'grade-high';  // da 6 a 8+ -> verde
  if (v >= 5)    return 'grade-mid';   // da 5 a 6- -> arancione
  return 'grade-low';                  // sotto 5 -> rosso
}
function fmt(v, d = 2) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toFixed(d);
}
function fmtDate(s) {
  if (!s) return '';
  try {
    return new Date(s).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: '2-digit' });
  } catch { return s; }
}

// ── Calcolo medie client-side ─────────────────────────────────────────────
function calcolaMediaGruppo(lista) {
  const vals = lista
    .filter(v => !v.non_fa_media)
    .map(v => v.valore)
    .filter(v => v !== null && v !== undefined && !isNaN(v));
  if (!vals.length) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function calcolaMediaPesata(lista, pesi) {
  const perTipo = {};
  for (const v of lista) {
    if (v.valore === null || v.valore === undefined) continue;
    const t = v.tipo || 'altro';
    if (!perTipo[t]) perTipo[t] = [];
    perTipo[t].push(v.valore);
  }
  let somma = 0, totPeso = 0;
  for (const [tipo, vals] of Object.entries(perTipo)) {
    const media = vals.reduce((a, b) => a + b, 0) / vals.length;
    // Mappa tipo → peso
    let peso = 0;
    if (tipo.includes('scritto') || tipo.includes('verifica') || tipo.includes('grafico')) peso = (pesi.scritto || 0) / 100;
    else if (tipo.includes('oral')) peso = (pesi.orale || 0) / 100;
    else if (tipo.includes('pratico') || tipo.includes('lab')) peso = (pesi.pratico || 0) / 100;
    else peso = (pesi.altro || 0) / 100;
    somma += media * peso;
    totPeso += peso;
  }
  if (totPeso === 0) return calcolaMediaGruppo(lista);
  return somma / totPeso;
}

function calcolaTutteLeMedie() {
  const grouped = {};
  for (const v of state.voti) {
    if (v.valore === null || v.valore === undefined) continue;
    if (!grouped[v.materia]) grouped[v.materia] = { 1: [], 2: [] };
    grouped[v.materia][v.periodo] = grouped[v.materia][v.periodo] || [];
    grouped[v.materia][v.periodo].push(v);
  }

  const medie = {};
  for (const [mat, periodi] of Object.entries(grouped)) {
    const fn = state.calcMode === 'weighted'
      ? lista => calcolaMediaPesata(lista, state.pesi)
      : lista => calcolaMediaGruppo(lista);

    const mp1 = periodi[1]?.length ? fn(periodi[1]) : null;
    const mp2 = periodi[2]?.length ? fn(periodi[2]) : null;
    let media = null;
    if (mp1 !== null && mp2 !== null) media = (mp1 + mp2) / 2;
    else if (mp1 !== null) media = mp1;
    else if (mp2 !== null) media = mp2;

    medie[mat] = {
      p1: mp1, p2: mp2, media,
      n_p1: periodi[1]?.length || 0,
      n_p2: periodi[2]?.length || 0,
    };
  }
  return medie;
}

function calcolaSummary(medie) {
  const votiNum = state.voti.filter(v => v.valore !== null && v.valore !== undefined);
  const p1 = votiNum.filter(v => v.periodo === 1).map(v => v.valore);
  const p2 = votiNum.filter(v => v.periodo === 2).map(v => v.valore);
  const mp1 = p1.length ? p1.reduce((a,b)=>a+b,0)/p1.length : null;
  const mp2 = p2.length ? p2.reduce((a,b)=>a+b,0)/p2.length : null;
  let tot = null;
  if (mp1 !== null && mp2 !== null) tot = (mp1 + mp2) / 2;
  else if (mp1 !== null) tot = mp1;
  else if (mp2 !== null) tot = mp2;
  return { media_p1: mp1, media_p2: mp2, media_totale: tot };
}

// ── Toast ─────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info', dur = 3500) {
  const c = $('#toastContainer');
  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.setAttribute('role', 'alert');
  el.innerHTML = `<span style="font-size:1.1rem;flex-shrink:0">${icons[type]||'ℹ'}</span><span>${msg}</span>`;
  c.appendChild(el);
  setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity .3s'; setTimeout(()=>el.remove(),300); }, dur);
}

// ── Loader ─────────────────────────────────────────────────────────────────
function setLoading(on) {
  const l = $('#loader');
  if (on) { l.classList.remove('hidden'); l.removeAttribute('aria-hidden'); }
  else    { l.classList.add('hidden'); l.setAttribute('aria-hidden','true'); }
}

// ── Status ─────────────────────────────────────────────────────────────────
function setStatus(s, txt) {
  $('#statusDot').className = `status-dot ${s}`;
  $('#statusText').textContent = txt;
}

// ── Theme ──────────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('cv_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('cv_theme', next);
  updateChartsTheme();
}
function getChartColors() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    grid: dark ? 'rgba(255,255,255,.06)' : 'rgba(0,0,0,.07)',
    text: dark ? '#94a3b8' : '#64748b',
    accent: '#3b82f6', p1: '#3b82f6', p2: '#10b981',
  };
}

// ── Fetch ──────────────────────────────────────────────────────────────────
async function fetchVoti() {
  setStatus('loading', 'Caricamento…');
  setLoading(true);
  try {
    const res = await fetch('/api/voti');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const data = await res.json();
    state.voti    = data.voti    || [];
    state.student = data.student || {};
    const source = (data._meta || {}).source || data._source;
    const age    = (data._meta || {}).cache_age_seconds;
    setStatus('online', source === 'csv' ? 'Da CSV' : 'Connesso');
    $('#dataSource').textContent = source === 'csv' ? '📁 CSV locale' : '';
    updateLastRefresh(age);
    return true;
  } catch (e) {
    setStatus('offline', 'Errore');
    showToast(`Errore: ${e.message}`, 'error');
    return false;
  } finally {
    setLoading(false);
  }
}

function updateLastRefresh(age) {
  const el = $('#lastRefresh');
  if (age === null || age === undefined) { el.textContent = ''; return; }
  const m = Math.floor(age / 60), s = Math.floor(age % 60);
  el.textContent = m > 0 ? `Cache: ${m}m ${s}s fa` : `Cache: ${s}s fa`;
}

// ── Refresh ────────────────────────────────────────────────────────────────
const doRefresh = throttle(async () => {
  const btn = $('#btnRefresh');
  btn.classList.add('btn-refresh-loading');
  btn.disabled = true;
  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();
    if (res.status === 429) { showToast(data.error, 'warning'); return; }
    if (!data.success) { showToast(data.error || 'Errore', 'error'); return; }
    await loadAll();
    showToast(`Aggiornato! ${data.voti_count} voti.`, 'success');
  } catch (e) {
    showToast(`Errore: ${e.message}`, 'error');
  } finally {
    btn.classList.remove('btn-refresh-loading');
    btn.disabled = false;
  }
}, 31000);

// ── Donut chart helpers ────────────────────────────────────────────────────
let chartDonutP1  = null;
let chartDonutP2  = null;
let chartDonutTot = null;

function donutColor(v) {
  if (v === null || v === undefined) return ['#64748b', '#1e293b'];
  if (v > 8.25)  return ['#60a5fa', '#1e3a5f'];  // blu (top)
  if (v >= 6)    return ['#10b981', '#064e3b'];   // verde
  if (v >= 5)    return ['#f59e0b', '#451a03'];   // arancione
  return ['#ef4444', '#450a0a'];                  // rosso
}

function renderDonut(canvasId, chartRef, value, label) {
  const canvas = $(canvasId);
  if (!canvas) return chartRef;
  const ctx = canvas.getContext('2d');
  const v = (value !== null && value !== undefined) ? Math.min(value, 10) : 0;
  const [fill, bg] = donutColor(value);
  const data = [v, 10 - v];

  if (chartRef) chartRef.destroy();
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data,
        backgroundColor: [fill, bg],
        borderWidth: 0,
        hoverOffset: 4,
      }]
    },
    options: {
      cutout: '72%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      animation: { duration: 600, easing: 'easeInOutQuart' },
    },
    plugins: [{
      id: 'centerText',
      afterDraw(chart) {
        const { ctx, chartArea: { width, height, left, top } } = chart;
        const cx = left + width / 2;
        const cy = top  + height / 2;
        ctx.save();
        // Valore
        const display = (value !== null && value !== undefined) ? fmt(value) : '—';
        ctx.font = `bold ${Math.min(width, height) * 0.22}px "DM Mono", monospace`;
        ctx.fillStyle = fill;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(display, cx, cy - height * 0.06);
        // Label
        ctx.font = `${Math.min(width, height) * 0.11}px "DM Sans", sans-serif`;
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(label, cx, cy + height * 0.14);
        ctx.restore();
      }
    }]
  });
}

// ── Render Summary ─────────────────────────────────────────────────────────
function renderSummary() {
  const medie = calcolaTutteLeMedie();
  const sum   = calcolaSummary(medie);

  // Donut charts
  chartDonutP1  = renderDonut('#donutP1',  chartDonutP1,  sum.media_p1,     'P1');
  chartDonutP2  = renderDonut('#donutP2',  chartDonutP2,  sum.media_p2,     'P2');
  chartDonutTot = renderDonut('#donutTot', chartDonutTot, sum.media_totale, 'Tot');

  const vNum = state.voti.filter(v => v.valore !== null && v.valore !== undefined);
  const p1n  = vNum.filter(v => v.periodo === 1).length;
  const p2n  = vNum.filter(v => v.periodo === 2).length;
  $('#nVotiP1').textContent  = p1n ? `${p1n} voti` : '';
  $('#nVotiP2').textContent  = p2n ? `${p2n} voti` : '';
  $('#nVotiTot').textContent = vNum.length ? `${vNum.length} voti` : '';
  $('#totalVotiCount').textContent = `${state.voti.length} voti totali`;

  // Benvenuto nome e classe
  const nome   = state.student.nome   || '';
  const classe = (state.student.classe && state.student.classe !== 'N/A' && state.student.classe !== 'null')
    ? state.student.classe : '';
  $('#studentNome').textContent = nome ? `Benvenuto, ${nome}` : '—';
  const classEl = $('#studentClasse');
  if (classe) {
    classEl.textContent = classe;
    classEl.style.display = '';
  } else {
    classEl.style.display = 'none';
  }

  return medie;
}

// ── Render Table ───────────────────────────────────────────────────────────
function renderTable(medie) {
  if (!medie) medie = calcolaTutteLeMedie();
  const tbody = $('#gradesBody');
  const q = state.searchQuery.toLowerCase();

  let entries = Object.entries(medie);
  if (q) entries = entries.filter(([m]) => m.toLowerCase().includes(q));

  entries.sort(([an, ad], [bn, bd]) => {
    let av, bv;
    if (state.sortCol === 'materia') { av = an; bv = bn; }
    else if (state.sortCol === 'p1')    { av = ad.p1    ?? -1; bv = bd.p1    ?? -1; }
    else if (state.sortCol === 'p2')    { av = ad.p2    ?? -1; bv = bd.p2    ?? -1; }
    else if (state.sortCol === 'media') { av = ad.media ?? -1; bv = bd.media ?? -1; }
    else { av = an; bv = bn; }
    if (typeof av === 'string') return state.sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    return state.sortDir === 'asc' ? av - bv : bv - av;
  });

  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">Nessun dato trovato.</td></tr>`;
    return;
  }

  tbody.innerHTML = entries.map(([mat, m]) => `
    <tr>
      <td>${mat}</td>
      <td class="grade-cell ${gradeClass(m.p1)}">${fmt(m.p1)}</td>
      <td class="grade-cell ${gradeClass(m.p2)}">${fmt(m.p2)}</td>
      <td class="grade-cell ${gradeClass(m.media)}">${fmt(m.media)}</td>
      <td style="color:var(--muted)">${m.n_p1 || 0}</td>
      <td style="color:var(--muted)">${m.n_p2 || 0}</td>
    </tr>`).join('');
}

// ── Render All Grades ──────────────────────────────────────────────────────
function renderRecentGrades() {
  const container = $('#recentGrades');
  const tutti = [...state.voti]
    .filter(v => v.data)
    .sort((a, b) => b.data.localeCompare(a.data));

  if (!tutti.length) {
    container.innerHTML = '<p style="color:var(--muted);font-size:.875rem">Nessun voto.</p>';
    return;
  }

  container.innerHTML = tutti.map(v => {
    // Controllo robusto null (JSON null -> JS null)
    const hasNum   = (v.valore !== null && v.valore !== undefined && v.valore !== 'null');
    const hasLtr   = (v.valore_lettera && v.valore_lettera !== 'null');
    const display  = hasNum ? v.valore : (hasLtr ? v.valore_lettera : '—');
    const colorCls = hasNum
      ? (v.non_fa_media ? 'grade-blue' : gradeClass(v.valore))
      : (hasLtr ? 'grade-lettera' : '');
    // Tipo: pulisci etichette interne CSS
    const tipoClean = (v.tipo || '')
      .replace('scritto/grafico', 'Scritto')
      .replace('scritto', 'Scritto')
      .replace('orale', 'Orale')
      .replace('pratico', 'Pratico')
      .replace('verifica', 'Verifica')
      .replace('voto test', 'Test')
      .replace('altro', '')
      || 'N/D';
    return `
    <div class="grade-pill">
      <div class="grade-pill-value ${colorCls}">${display}</div>
      <div class="grade-pill-info">
        <div class="grade-pill-materia" title="${v.materia}">${v.materia}</div>
        <div class="grade-pill-meta">
          <span>${fmtDate(v.data)}</span>
          <span class="tipo-badge">${tipoClean}</span>
          <span>P${v.periodo}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

// ── Charts ─────────────────────────────────────────────────────────────────
function populateMateriaFilter() {
  const sel = $('#filterMateria');
  const materie = [...new Set(state.voti.map(v => v.materia))].sort();
  sel.innerHTML = '<option value="all">Tutte le materie</option>';
  materie.forEach(m => {
    const o = document.createElement('option');
    o.value = m; o.textContent = m;
    sel.appendChild(o);
  });
}

function renderLineChart() {
  const ctx = $('#chartLine').getContext('2d');
  const c = getChartColors();

  let filtered = state.voti.filter(v => v.data && v.valore !== null && v.valore !== undefined);
  if (state.filterMateria !== 'all') filtered = filtered.filter(v => v.materia === state.filterMateria);
  filtered.sort((a, b) => a.data.localeCompare(b.data));

  const materieSet = state.filterMateria === 'all'
    ? [...new Set(filtered.map(v => v.materia))]
    : [state.filterMateria];

  const colors = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#f97316','#14b8a6','#a855f7','#ec4899'];

  const datasets = materieSet.map((mat, i) => {
    const votiMat = filtered.filter(v => v.materia === mat);
    return {
      label: mat,
      data: votiMat.map(v => v.valore),
      labels: votiMat.map(v => fmtDate(v.data)),
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length] + '22',
      borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
      tension: .35, fill: materieSet.length === 1,
    };
  });

  // Usa etichette categoriali (no time scale - non serve adapter)
  const allLabels = [...new Set(filtered.map(v => fmtDate(v.data)))];

  if (chartLine) chartLine.destroy();
  chartLine = new Chart(ctx, {
    type: 'line',
    data: {
      labels: allLabels,
      datasets: datasets.map((ds, i) => {
        const mat = materieSet[i];
        const votiMat = filtered.filter(v => v.materia === mat);
        const data = allLabels.map(lbl => {
          const v = votiMat.find(v => fmtDate(v.data) === lbl);
          return v ? v.valore : null;
        });
        return { ...ds, data, spanGaps: false };
      }),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: c.text, usePointStyle: true, padding: 16, font: { size: 11 } } }
      },
      scales: {
        x: { grid: { color: c.grid }, ticks: { color: c.text, font: { size: 10 }, maxRotation: 45, maxTicksLimit: 12 } },
        y: { min: 0, max: 10, grid: { color: c.grid }, ticks: { color: c.text, stepSize: 1 } }
      }
    }
  });
}

function renderBarChart() {
  const ctx = $('#chartBar').getContext('2d');
  const c = getChartColors();
  const medie = calcolaTutteLeMedie();
  const materie = Object.keys(medie).sort();

  if (chartBar) chartBar.destroy();
  chartBar = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: materie.map(m => m.length > 18 ? m.slice(0, 18) + '…' : m),
      datasets: [
        { label: 'Periodo 1', data: materie.map(m => medie[m].p1 ?? 0),
          backgroundColor: c.p1 + 'cc', borderColor: c.p1, borderWidth: 1, borderRadius: 6 },
        { label: 'Periodo 2', data: materie.map(m => medie[m].p2 ?? 0),
          backgroundColor: c.p2 + 'cc', borderColor: c.p2, borderWidth: 1, borderRadius: 6 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: c.text, usePointStyle: true, padding: 16, font: { size: 11 } } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: c.text, font: { size: 10 }, maxRotation: 45 } },
        y: { min: 0, max: 10, grid: { color: c.grid }, ticks: { color: c.text, stepSize: 1 } }
      }
    }
  });
}

function updateChartsTheme() {
  if (state.voti.length) { renderLineChart(); renderBarChart(); }
}

// ── Sort ───────────────────────────────────────────────────────────────────
function handleSort(col) {
  if (state.sortCol === col) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
  else { state.sortCol = col; state.sortDir = 'asc'; }
  $$('.sortable').forEach(th => th.setAttribute('aria-sort', 'none'));
  const active = $(`.sortable[data-col="${col}"]`);
  if (active) active.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
  renderTable();
}

// ── Export ─────────────────────────────────────────────────────────────────
function exportCSV(type = 'raw') { window.location.href = `/api/export/csv?type=${type}`; }

// ── Load All ───────────────────────────────────────────────────────────────
async function loadAll() {
  const ok = await fetchVoti();
  if (!ok) return;
  const medie = renderSummary();
  renderTable(medie);
  renderRecentGrades();
  populateMateriaFilter();
  renderLineChart();
  renderBarChart();
}

// ── Pesi ───────────────────────────────────────────────────────────────────
function updatePesiSum() {
  const s = parseInt($('#pesoScritto').value) || 0;
  const o = parseInt($('#pesoOrale').value)   || 0;
  const p = parseInt($('#pesoPratico').value) || 0;
  const tot = s + o + p;
  $('#pesiSum').textContent = tot;
  const warn = $('#pesiWarning');
  if (tot !== 100) warn.removeAttribute('hidden'); else warn.setAttribute('hidden','');
  return tot === 100;
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  loadAll();

  $('#btnTheme').addEventListener('click', toggleTheme);
  $('#btnRefresh').addEventListener('click', doRefresh);
  $('#btnExportRaw').addEventListener('click', () => exportCSV('raw'));
  $('#btnExportMedie').addEventListener('click', () => exportCSV('medie'));

  $('#calcMode').addEventListener('change', e => {
    state.calcMode = e.target.value;
    const pp = $('#pesiPanel');
    if (state.calcMode === 'weighted') { pp.removeAttribute('hidden'); pp.removeAttribute('aria-hidden'); }
    else { pp.setAttribute('hidden',''); pp.setAttribute('aria-hidden','true'); }
    const medie = renderSummary();
    renderTable(medie);
    renderBarChart();
  });

  ['#pesoScritto','#pesoOrale','#pesoPratico'].forEach(s => $(s).addEventListener('input', updatePesiSum));

  $('#btnApplyPesi').addEventListener('click', () => {
    if (!updatePesiSum()) { showToast('La somma dei pesi deve essere 100%!', 'warning'); return; }
    state.pesi.scritto  = parseInt($('#pesoScritto').value) || 0;
    state.pesi.verifica = state.pesi.scritto;
    state.pesi.orale    = parseInt($('#pesoOrale').value)   || 0;
    state.pesi.pratico  = parseInt($('#pesoPratico').value) || 0;
    const medie = renderSummary();
    renderTable(medie);
    renderBarChart();
    showToast('Pesi applicati!', 'success');
  });

  $('#searchMateria').addEventListener('input', debounce(e => {
    state.searchQuery = e.target.value;
    renderTable();
  }, 200));

  $('#filterMateria').addEventListener('change', e => {
    state.filterMateria = e.target.value;
    renderLineChart();
  });

  $$('.sortable').forEach(th => {
    th.addEventListener('click', () => handleSort(th.dataset.col));
    th.addEventListener('keydown', e => { if (e.key==='Enter'||e.key===' ') { e.preventDefault(); handleSort(th.dataset.col); } });
  });

  $('#csvUpload').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const res = await fetch('/api/upload_csv', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      showToast(`CSV caricato: ${data.voti_count} voti`, 'success');
      await loadAll();
    } catch (e) { showToast(`Errore: ${e.message}`, 'error'); }
  });

  $('#closeBanner').addEventListener('click', () => $('#uploadBanner').classList.add('hidden'));
});
