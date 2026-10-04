/* Interface de prévisualisation : aucune requête d'inférence ni crédit simulé.
   Le flux SSE de frontend/static/js/chat.js reste la référence pour les futurs
   événements content / reasoning / tool_status, mais n'est pas branché ici. */
(() => {
  const $ = id => document.getElementById(id);
  const panel = $('settings-panel');
  const trigger = $('settings-trigger');
  const overlay = $('settings-overlay');
  const closeButton = $('settings-close');
  const filter = $('row-filter');
  const sort = $('row-sort');
  const rows = $('activity-rows');
  const dialog = $('detail-dialog');
  let activities = [];
  let lastFocus = null;
  let language = 'fr';
  const labels = {
    fr: { load: 'Chargement…', empty: 'Aucune activité trouvée.', error: 'Impossible de charger les activités.', detailError: 'Impossible de charger les détails.', duration: 'Durée', distance: 'Distance', power: 'Puissance moyenne', heart: 'FC moyenne', sport: 'Sport', elevation: 'Dénivelé', activity: 'Activité' },
    en: { load: 'Loading…', empty: 'No activities found.', error: 'Unable to load activities.', detailError: 'Unable to load details.', duration: 'Duration', distance: 'Distance', power: 'Average power', heart: 'Average HR', sport: 'Sport', elevation: 'Elevation', activity: 'Activity' }
  };

  function open() {
    lastFocus = document.activeElement;
    overlay.hidden = false;
    panel.inert = false;
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    trigger.setAttribute('aria-expanded', 'true');
    closeButton.focus();
    if (!activities.length) loadActivities();
  }
  function close() {
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
    panel.inert = true;
    trigger.setAttribute('aria-expanded', 'false');
    overlay.hidden = true;
    (lastFocus || trigger).focus();
  }
  trigger.addEventListener('click', open);
  closeButton.addEventListener('click', close);
  overlay.addEventListener('click', close);
  panel.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const elements = [...panel.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled])')];
    const first = elements[0], last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (dialog.open) dialog.close();
      else if (panel.classList.contains('open')) close();
    }
  });
  $('chat-form').addEventListener('submit', event => event.preventDefault());
  $('language-select').addEventListener('change', event => {
    language = event.target.value === 'en' ? 'en' : 'fr';
    document.documentElement.lang = language;
    // UI only. The server-side LM handler will receive the saved language later.
    render();
  });
  filter.addEventListener('input', render);
  sort.addEventListener('change', render);
  $('detail-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });

  function cell(tr, text) {
    const td = document.createElement('td'); td.textContent = text ?? '—'; tr.appendChild(td); return td;
  }
  function number(value, suffix = '') {
    return value == null ? '—' : `${Number(value).toLocaleString(language, { maximumFractionDigits: 1 })}${suffix}`;
  }
  function date(value) {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.valueOf()) ? '—' : d.toLocaleString(language, { dateStyle: 'short', timeStyle: 'short' });
  }
  function render() {
    rows.replaceChildren();
    const needle = filter.value.toLocaleLowerCase().trim();
    const list = activities.filter(a => `${a.name || ''} ${a.sport_type || ''}`.toLocaleLowerCase().includes(needle));
    list.sort((a,b) => sort.value === 'title'
      ? (a.name || '').localeCompare(b.name || '', language)
      : (sort.value === 'oldest' ? 1 : -1) * ((Date.parse(a.start_date_local || a.start_date) || 0) - (Date.parse(b.start_date_local || b.start_date) || 0)));
    if (!list.length) { const tr = document.createElement('tr'); const td = cell(tr, labels[language].empty); td.colSpan = 5; rows.appendChild(tr); return; }
    for (const activity of list) {
      const tr = document.createElement('tr'); tr.tabIndex = 0;
      cell(tr, date(activity.start_date_local || activity.start_date));
      const type = cell(tr, `🚴 ${activity.sport_type || labels[language].activity}`);
      type.className = 'type-icon';
      cell(tr, activity.name || '—');
      cell(tr, number(activity.moving_time_min, ' min'));
      cell(tr, number(activity.distance_km, ' km'));
      tr.addEventListener('click', () => showDetail(activity));
      tr.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showDetail(activity); } });
      rows.appendChild(tr);
    }
  }
  async function loadActivities() {
    try {
      const response = await fetch('/api/activities/?limit=500', { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      activities = await response.json();
      if (!Array.isArray(activities)) throw new Error('Unexpected response');
      render();
    } catch (_) {
      rows.replaceChildren(); const tr = document.createElement('tr'); const td = cell(tr, labels[language].error); td.colSpan = 5; rows.appendChild(tr);
    }
  }
  async function showDetail(activity) {
    $('detail-title').textContent = activity.name || labels[language].activity;
    $('detail-body').textContent = labels[language].load;
    dialog.showModal();
    try {
      const response = await fetch(`/api/activities/${encodeURIComponent(activity.id)}`, { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const detail = await response.json();
      const dl = document.createElement('dl');
      for (const [label, value] of [
        [labels[language].sport, detail.sport_type || '—'],
        [labels[language].duration, number(detail.moving_time_min, ' min')],
        [labels[language].distance, number(detail.distance_km, ' km')],
        [labels[language].elevation, number(detail.elevation_gain_m, ' m')],
        [labels[language].power, number(detail.avg_watts, ' W')],
        [labels[language].heart, number(detail.avg_heartrate, ' bpm')]
      ]) { const wrapper = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = label; dd.textContent = value; wrapper.append(dt, dd); dl.appendChild(wrapper); }
      $('detail-body').replaceChildren(dl);
    } catch (_) { $('detail-body').textContent = labels[language].detailError; }
  }
})();
