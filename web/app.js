/* ===== NEVO · frontend conectado al backend Python ===== */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

async function api(path, opts) {
  const res = await fetch(path, opts);
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || res.statusText);
  return data;
}

/* ---- Toasts ---- */
function toast(msg, kind = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = msg;
  $('#toastWrap').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s';
    setTimeout(() => t.remove(), 300); }, kind === 'err' ? 5200 : 3200);
}

/* ---- Screen routing ---- */
function showScreen(name) {
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === name));
  $$('.nav a').forEach(a => a.classList.toggle('active', a.dataset.screen === name));
  if (name === 'biblioteca') loadLibrary();
  if (name === 'revision')   refreshReview();
  window.scrollTo(0, 0);
}
$$('[data-screen]').forEach(a => a.addEventListener('click', e => {
  if (a.tagName === 'A') e.preventDefault();
  showScreen(a.dataset.screen);
}));

/* ============ Extractor ============ */
let mode = 'gratis';
$$('.opt-card').forEach(c => c.addEventListener('click', () => {
  $$('.opt-card').forEach(o => o.classList.remove('sel'));
  c.classList.add('sel');
  mode = c.dataset.mode;
  $('#iaExtra').classList.toggle('show', mode === 'ia');
}));

let pdfToken = null;        // token del PDF subido al backend
$('#pdfInput').addEventListener('change', async e => {
  const f = e.target.files[0];
  if (!f) { $('#pdfName').textContent = 'Ningún archivo seleccionado'; pdfToken = null; return; }
  $('#pdfName').textContent = 'Subiendo ' + f.name + '…';
  try {
    const fd = new FormData();
    fd.append('pdf', f, f.name);
    const r = await api('/api/upload', { method: 'POST', body: fd });
    pdfToken = r.token;
    $('#pdfName').textContent = f.name;
    $('#urlInput').value = '';
  } catch (err) {
    pdfToken = null;
    $('#pdfName').textContent = 'No se pudo subir el PDF';
    toast('Error subiendo el PDF: ' + err.message, 'err');
  }
});

/* Pasos visuales (alineados con las fases reales del backend) */
const steps = [
  'Conectando con la fuente',
  'Descargando la revista',
  'Renderizando páginas a imagen',
  'Detección de anuncios',
  'Cruzando contactos y deduplicando',
  'Marcando casos dudosos',
];
const STEP_PCT = [8, 22, 38, 70, 88, 100];
const checkSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M4 12l5 5L20 6"/></svg>';
function renderSteps(state) {
  const list = $('#stepsList');
  list.innerHTML = '';
  steps.forEach((label, i) => {
    let cls = 'idle',
        ico = '<span style="width:7px;height:7px;border-radius:50%;background:currentColor;opacity:.5"></span>',
        time = '';
    if (state > i)        { cls = 'done';   ico = checkSvg;                 time = 'Hecho'; }
    else if (state === i) { cls = 'active'; ico = '<span class="spinner"></span>'; time = 'En curso…'; }
    const row = document.createElement('div');
    row.className = 'step-row ' + cls;
    row.innerHTML = `<span class="step-ico">${ico}</span><span class="step-tx">${label}</span><span class="step-time">${time}</span>`;
    list.appendChild(row);
  });
}
renderSteps(-1);

let polling = false;
$('#extractBtn').addEventListener('click', startExtraction);

async function startExtraction() {
  if (polling) return;
  const url = $('#urlInput').value.trim();
  if (!url && !pdfToken) { toast('Indica una URL o sube un PDF.', 'err'); return; }
  const apiKey = $('#apiKey').value.trim();
  if (mode === 'ia' && !apiKey && !window.__hasSavedKey) {
    toast('El modo IA necesita una clave de API de Anthropic.', 'err'); return;
  }

  const btn = $('#extractBtn');
  btn.disabled = true; btn.style.opacity = .65;
  $('#resultBanner').classList.remove('show');
  $('#progState').textContent = 'Analizando la revista…';
  $('#progLog').classList.add('show'); $('#progLog').textContent = '';
  renderSteps(0);
  $('#pctLabel').textContent = '0%'; $('#pfill').style.width = '4%';

  try {
    await api('/api/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url, pdf_token: pdfToken, mode, api_key: apiKey,
        remember: $('#rememberKey').checked,
      }),
    });
  } catch (err) {
    toast('No se pudo iniciar: ' + err.message, 'err');
    btn.disabled = false; btn.style.opacity = 1;
    return;
  }
  polling = true;
  pollStatus();
}

async function pollStatus() {
  let st;
  try { st = await api('/api/status'); }
  catch { setTimeout(pollStatus, 800); return; }

  if (st.messages) $('#progLog').textContent = st.messages.join('\n');
  $('#progLog').scrollTop = $('#progLog').scrollHeight;
  if (st.message) $('#progState').textContent = st.message;

  const step = Math.max(0, st.step);
  renderSteps(st.state === 'done' ? steps.length : step);
  const pct = st.state === 'done' ? 100 : STEP_PCT[Math.min(step, STEP_PCT.length - 1)];
  $('#pfill').style.width = pct + '%';
  $('#pctLabel').textContent = st.state === 'done' ? 'Completado' : pct + '%';

  if (st.state === 'running') { setTimeout(pollStatus, 700); return; }

  polling = false;
  const btn = $('#extractBtn');
  btn.disabled = false; btn.style.opacity = 1;

  if (st.state === 'error') {
    $('#progState').textContent = 'La extracción ha fallado.';
    toast(st.error || 'Error en la extracción', 'err');
    return;
  }
  // done
  const s = st.summary || { total: 0, flagged: 0 };
  $('#progState').textContent = 'Extracción finalizada correctamente.';
  $('#rbTitle').textContent = `${s.total} anunciantes extraídos`;
  $('#rbSub').textContent = s.flagged
    ? `${s.total - s.flagged} con confianza alta · ${s.flagged} marcados para revisar`
    : 'Ninguno requiere revisión manual';
  const goBtn = $('#goReview');
  if (s.flagged) {
    goBtn.style.display = '';
    goBtn.textContent = 'Revisar dudosos';
  } else {
    goBtn.style.display = 'none';
  }
  $('#resultBanner').classList.add('show');
}
$('#goReview').addEventListener('click', () => showScreen('revision'));

/* ============ Revisión ============ */
let review = { items: [], states: [], cur: 0, loaded: false };

async function refreshReview() {
  try {
    const data = await api('/api/review');
    review.items = data.items || [];
    review.meta = data.meta || {};
    if (!review.statesValid || review.states.length !== review.items.length) {
      review.states = review.items.map(() => 'pending');
      review.statesValid = true;
    }
    review.cur = 0;
    review.loaded = true;
  } catch { review.items = []; }

  const has = review.items.length > 0;
  $('#reviewDetail').style.display = has ? '' : 'none';
  $('#reviewEmpty').style.display  = has ? 'none' : '';
  $('.queue').style.display = has ? '' : 'none';
  $('#revChip').textContent = `${review.items.length} por revisar`;
  if (review.meta && review.meta.titulo)
    $('#revCrumb').textContent = review.meta.titulo;
  if (has) { renderQueue(); loadDetail(); }
}

function renderQueue() {
  const list = $('#queueList');
  list.innerHTML = '';
  let pending = 0;
  review.items.forEach((d, i) => {
    const decided = review.states[i] !== 'pending';
    if (!decided) pending++;
    const el = document.createElement('div');
    el.className = 'q-item' + (i === review.cur ? ' sel' : '') + (decided ? ' done' : '');
    el.innerHTML = `<span class="q-dot"></span>
      <span class="q-name">${esc(d.brand)}</span>
      <span class="q-conf">${Math.round((d.confidence || 0) * 100)}%</span>
      <span class="q-pg">p.${d.pages && d.pages.length ? d.pages[0] : '–'}</span>`;
    el.addEventListener('click', () => { saveEdits(); review.cur = i; loadDetail(); });
    list.appendChild(el);
  });
  $('#queueCount').textContent = pending + ' pendientes';
}

function loadDetail() {
  const d = review.items[review.cur];
  if (!d) return;
  $('#fMarca').value  = d.brand   || '';
  $('#fSector').value = d.sector  || '';
  $('#fWeb').value    = d.website || '';
  $('#fEmail').value  = d.email   || '';
  $('#fTel').value    = d.phone   || '';
  $('#fTam').value    = d.ad_size || '';
  $('#detFlag').textContent = d.review_label || d.review_flag || '—';
  $('#detStatus').textContent = ({ pending: 'Pendiente', keep: 'Confirmado', drop: 'Descartado' })[review.states[review.cur]];
  $('#detPager').textContent =
    String(review.cur + 1).padStart(2, '0') + ' / ' + String(review.items.length).padStart(2, '0');

  // previa real de la página
  const img = $('#adImg');
  const prev = $('#reviewPreview');
  const pg = d.pages && d.pages.length ? d.pages[0] : null;
  if (pg != null) {
    img.hidden = false; prev.classList.remove('empty');
    img.onerror = () => { img.hidden = true; prev.classList.add('empty'); prev.dataset.msg = 'Previa no disponible'; };
    img.src = '/api/page?n=' + pg + '&t=' + Date.now();
  } else {
    img.hidden = true; prev.classList.add('empty');
  }
  renderQueue();
}

function saveEdits() {
  const d = review.items[review.cur];
  if (!d) return;
  d.brand   = $('#fMarca').value.trim();
  d.sector  = $('#fSector').value.trim();
  d.website = $('#fWeb').value.trim();
  d.email   = $('#fEmail').value.trim();
  d.phone   = $('#fTel').value.trim();
  d.ad_size = $('#fTam').value.trim();
}

function advance() {
  const next = review.items.findIndex((_, i) => review.states[i] === 'pending');
  if (next === -1) { renderQueue(); return; }
  review.cur = next; loadDetail();
}
$('#confirmBtn').addEventListener('click', () => {
  saveEdits(); review.states[review.cur] = 'keep'; advance();
});
$('#discardBtn').addEventListener('click', () => {
  review.states[review.cur] = 'drop'; advance();
});
$('#skipBtn').addEventListener('click', () => {
  saveEdits(); review.cur = (review.cur + 1) % review.items.length; loadDetail();
});

$('#exportBtn').addEventListener('click', async () => {
  saveEdits();
  const btn = $('#exportBtn');
  btn.disabled = true; btn.style.opacity = .65;
  btn.innerHTML = '<span class="spinner"></span> Generando…';
  try {
    const decisions = review.items.map((d, i) => ({
      index: d.index, state: review.states[i],
      fields: { brand: d.brand, sector: d.sector, website: d.website,
                email: d.email, phone: d.phone, ad_size: d.ad_size },
    }));
    const r = await api('/api/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decisions }),
    });
    toast(`Informe generado · ${r.n} anunciantes`, 'ok');
    review.statesValid = false;
    await refreshReview();
    loadLibrary();
  } catch (err) {
    toast('No se pudo generar el informe: ' + err.message, 'err');
  } finally {
    btn.disabled = false; btn.style.opacity = 1;
    btn.innerHTML = 'Terminar y generar informe <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14m0 0l-6-6m6 6l-6 6"/></svg>';
  }
});

/* ============ Biblioteca ============ */
let issues = [];
const picked = [];

async function loadLibrary() {
  try {
    const data = await api('/api/library');
    issues = data.issues || [];
  } catch { issues = []; }
  picked.length = 0;
  $('#compareBtn').disabled = true;
  $('#savedChip').textContent = issues.length + (issues.length === 1 ? ' número guardado' : ' números guardados');
  updateSelHint();
  renderIssues($('#libSearch').value || '');
}

function renderIssues(filter = '') {
  const list = $('#issueList');
  list.innerHTML = '';
  const f = filter.toLowerCase();
  const shown = issues.filter(it =>
    ((it.name || '') + (it.n || '') + (it.sub || '')).toLowerCase().includes(f));
  if (!shown.length) {
    list.innerHTML = `<div class="empty-state"><div class="es-t">${issues.length ? 'Sin resultados' : 'Biblioteca vacía'}</div><div class="es-s">${issues.length ? 'Prueba otra búsqueda.' : 'Analiza una revista y se guardará aquí automáticamente.'}</div></div>`;
    return;
  }
  shown.forEach(it => {
    const idx = issues.indexOf(it);
    const pi = picked.indexOf(idx);
    const delta = it.prev == null ? null : it.count - it.prev;
    const dCls = delta == null ? 'flat' : delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
    const dTxt = delta == null ? '·' : delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '=';
    const row = document.createElement('div');
    row.className = 'issue' + (pi > -1 ? ' picked' : '');
    row.innerHTML = `
      <div class="pick">${pi > -1 ? (pi === 0 ? 'A' : 'B') : ''}</div>
      <div class="num">${esc(it.n)}</div>
      <div><div class="iname">${esc(it.name)}</div><div class="isub">${esc(it.sub || '')}</div></div>
      <div class="icount">${it.count} <span>anunc.</span></div>
      <div class="idate">${esc(it.date || '')}</div>
      <div class="idelta ${dCls}">${dTxt}</div>`;
    row.addEventListener('click', () => togglePick(idx));
    list.appendChild(row);
  });
}

function togglePick(idx) {
  const at = picked.indexOf(idx);
  if (at > -1) picked.splice(at, 1);
  else { if (picked.length >= 2) picked.shift(); picked.push(idx); }
  $('#compareBtn').disabled = picked.length !== 2;
  updateSelHint();
  renderIssues($('#libSearch').value);
}

function updateSelHint() {
  $('#selHint').innerHTML = picked.length === 2
    ? `Comparando <b>${esc(issues[picked[0]].n)}</b> → <b>${esc(issues[picked[1]].n)}</b> · listo`
    : `Selecciona <b>2 números</b> para comparar · <b>${picked.length}</b> seleccionado${picked.length === 1 ? '' : 's'}`;
}

$('#libSearch').addEventListener('input', e => renderIssues(e.target.value));

$('#compareBtn').addEventListener('click', async () => {
  if (picked.length !== 2) return;
  // picked[0] = A (anterior), picked[1] = B (actual)
  const id_a = issues[picked[0]].id, id_b = issues[picked[1]].id;
  const btn = $('#compareBtn');
  btn.disabled = true;
  try {
    await api('/api/library/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_a, id_b }),
    });
    toast('Comparativa abierta en el navegador', 'ok');
  } catch (err) {
    toast('No se pudo comparar: ' + err.message, 'err');
  } finally { btn.disabled = picked.length !== 2; }
});

$('#viewBtn').addEventListener('click', async () => {
  if (picked.length !== 1) { toast('Selecciona UN número para ver sus anunciantes.', 'err'); return; }
  const it = issues[picked[0]];
  try {
    const data = await api('/api/library/view?id=' + it.id);
    openModal(`${it.n} · ${data.advertisers.length} anunciantes`,
      data.advertisers.map(a =>
        `<div class="modal-row"><span class="mr-b">${esc(a.brand)}</span><span class="mr-s">${esc(a.sector || 'sin sector')}</span></div>`
      ).join('') || '<div class="empty-state"><div class="es-s">Sin anunciantes.</div></div>');
  } catch (err) { toast('No se pudo cargar: ' + err.message, 'err'); }
});

/* ---- Modal ---- */
function openModal(title, html) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = html;
  $('#modalBack').classList.add('show');
}
$('#modalClose').addEventListener('click', () => $('#modalBack').classList.remove('show'));
$('#modalBack').addEventListener('click', e => { if (e.target.id === 'modalBack') $('#modalBack').classList.remove('show'); });

/* ---- util ---- */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

/* ---- init: precarga config (URL e indicio de clave) ---- */
(async () => {
  try {
    const cfg = await api('/api/config');
    $('#urlInput').value = cfg.last_url || 'https://www.proarquitectura.es/proarquitectura-206-especial-arquitectura-industrializada/';
    window.__hasSavedKey = !!cfg.has_key;
    if (cfg.has_key) {
      $('#apiKey').placeholder = 'Clave guardada · déjala vacía para reutilizarla';
      $('#rememberKey').checked = true;
    }
  } catch {
    $('#urlInput').value = 'https://www.proarquitectura.es/proarquitectura-206-especial-arquitectura-industrializada/';
  }
})();
