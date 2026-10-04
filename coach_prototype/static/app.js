/* No external LLM, Strava or payment calls: this is an explicit demo. */
(() => {
  const $ = id => document.getElementById(id);
  const panel = $('settings-panel'), trigger = $('open-settings'), overlay = $('overlay');
  const table = $('timeline'), dialog = $('detail');
  let items = [], lang = 'fr', busy = false, previousFocus;
  const copy = {
    fr: { load: 'Chargement…', empty: 'Aucun résultat.', error: 'Impossible de charger les données.', detailError: 'Détails indisponibles.', activity: 'Activité', artifact: 'Document MD', demo: 'Réponse simulée : je pourrai comparer un document de séance aux activités enregistrées lorsque le coach IA sera connecté. Pour le moment, consultez les exemples dans vos paramètres.' },
    en: { load: 'Loading…', empty: 'No results.', error: 'Unable to load data.', detailError: 'Details unavailable.', activity: 'Activity', artifact: 'Markdown note', demo: 'Simulated reply: I will be able to compare a training note with recorded activities once the AI coach is connected. For now, browse the examples in settings.' }
  };
  function open() {
    previousFocus = document.activeElement; overlay.hidden = false; panel.inert = false;
    panel.classList.add('open'); panel.setAttribute('aria-hidden','false'); trigger.setAttribute('aria-expanded','true');
    $('close-settings').focus();
    if (!items.length) load();
  }
  function close() {
    panel.classList.remove('open'); panel.setAttribute('aria-hidden','true'); panel.inert = true;
    overlay.hidden = true; trigger.setAttribute('aria-expanded','false'); (previousFocus || trigger).focus();
  }
  trigger.addEventListener('click',open); $('close-settings').addEventListener('click',close); overlay.addEventListener('click',close);
  panel.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const focusable = [...panel.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled])')];
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { if (dialog.open) dialog.close(); else if (panel.classList.contains('open')) close(); } });
  $('detail-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  $('language').addEventListener('change', event => { lang = event.target.value === 'en' ? 'en' : 'fr'; document.documentElement.lang = lang; render(); });
  $('filter').addEventListener('input',render); $('sort').addEventListener('change',render);

  function num(value, unit='') { return value == null ? '—' : `${Number(value).toLocaleString(lang, {maximumFractionDigits:1})}${unit}`; }
  function date(value) { const d = new Date(value); return Number.isNaN(+d) ? '—' : d.toLocaleString(lang, {dateStyle:'short',timeStyle:'short'}); }
  function cell(row,text) { const td = document.createElement('td'); td.textContent = text ?? '—'; row.appendChild(td); return td; }
  function message(text) { table.replaceChildren(); const row = document.createElement('tr'); cell(row,text).colSpan = 5; table.appendChild(row); }
  function render() {
    const query = $('filter').value.trim().toLocaleLowerCase();
    const list = items.filter(i => `${i.title} ${i.subtype} ${i.type}`.toLocaleLowerCase().includes(query));
    list.sort((a,b) => $('sort').value === 'title'
      ? a.title.localeCompare(b.title,lang)
      : ($('sort').value === 'recent' ? -1 : 1) * (Date.parse(a.date)-Date.parse(b.date)));
    if (!list.length) { message(copy[lang].empty); return; }
    table.replaceChildren();
    list.forEach(item => {
      const tr = document.createElement('tr'); tr.tabIndex = 0;
      cell(tr,date(item.date));
      cell(tr,`${item.type === 'artifact' ? '📄' : '🔶'} ${item.type === 'artifact' ? copy[lang].artifact : copy[lang].activity}`);
      cell(tr,item.title); cell(tr,num(item.duration_minutes,' min')); cell(tr,num(item.distance_km,' km'));
      tr.addEventListener('click', () => detail(item));
      tr.addEventListener('keydown',e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); detail(item); } });
      table.appendChild(tr);
    });
  }
  async function load() {
    try {
      const response = await fetch('/api/timeline', {credentials:'same-origin'});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      items = await response.json(); if (!Array.isArray(items)) throw Error('Invalid response'); render();
    } catch (_) { message(copy[lang].error); }
  }
  async function detail(item) {
    $('detail-title').textContent = item.title; $('detail-body').textContent = copy[lang].load; dialog.showModal();
    try {
      const response = await fetch(`/api/timeline/${item.type}/${encodeURIComponent(item.id)}`, {credentials:'same-origin'});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const data = await response.json(), body = $('detail-body'); body.replaceChildren();
      if (item.type === 'artifact') {
        const pre = document.createElement('pre'); pre.className = 'markdown'; pre.textContent = data.markdown; body.appendChild(pre);
        const download = document.createElement('button'); download.textContent = 'Télécharger .md'; download.type = 'button';
        download.addEventListener('click', () => {
          const url = URL.createObjectURL(new Blob([data.markdown], {type:'text/markdown;charset=utf-8'}));
          const link = document.createElement('a'); link.href = url; link.download = `document-${item.id}.md`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
        }); body.appendChild(download);
      } else {
        const dl = document.createElement('dl');
        [['Date',date(data.date)],['Durée',num(data.duration_minutes,' min')],['Distance',num(data.distance_km,' km')],['Puissance',num(data.avg_watts,' W')],['Note',data.notes || '—']].forEach(([label,value]) => {
          const div = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent=label; dd.textContent=value; div.append(dt,dd); dl.appendChild(div);
        }); body.appendChild(dl);
      }
    } catch (_) { $('detail-body').textContent = copy[lang].detailError; }
  }
  function addMessage(role,text,simulate=false) {
    const row = document.createElement('div'); row.className=`message ${role}`;
    const icon=document.createElement('span'); icon.className='icon'; icon.textContent=role==='user'?'👤':'🤖';
    const bubble=document.createElement('div'); bubble.className='bubble'; bubble.textContent=text;
    if (simulate) {
      const details=document.createElement('details'); details.className='reasoning';
      const summary=document.createElement('summary'); summary.textContent='💭 Scénario de démonstration (pas de réflexion du modèle)';
      const note=document.createElement('pre'); note.textContent='Réponse prédéfinie ; aucune requête d’inférence ni consultation de la base par un modèle.';
      details.append(summary,note);
      const status=document.createElement('div'); status.className='tool-status'; status.textContent='🔧 Outils non appelés — aperçu visuel';
      bubble.append(details,status);
    }
    row.append(icon,bubble); $('messages').appendChild(row); $('messages').scrollTop=$('messages').scrollHeight;
  }
  $('chat-input').addEventListener('input',event => { event.target.style.height='auto'; event.target.style.height=Math.min(event.target.scrollHeight,130)+'px'; });
  $('chat-input').addEventListener('keydown',event => { if (event.key==='Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); } });
  $('chat-form').addEventListener('submit',event => {
    event.preventDefault(); if (busy) return;
    const input=$('chat-input'), text=input.value.trim(); if (!text) return;
    busy=true; addMessage('user',text); input.value=''; input.style.height='auto';
    setTimeout(() => { addMessage('assistant',copy[lang].demo,true); busy=false; },350);
  });
})();
