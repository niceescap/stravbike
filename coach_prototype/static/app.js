/* Demo conversation is local-only. Strava activity calls use the authenticated
   Coach session; no LLM request is made by this prototype. */
(() => {
  const $ = id => document.getElementById(id);
  const panel = $('settings-panel'), trigger = $('open-settings'), overlay = $('overlay');
  const table = $('timeline'), dialog = $('detail');
  let items = [], lang = 'fr', busy = false, previousFocus;
  const copy = {
    fr: { load: 'Chargement…', empty: 'Aucun résultat.', error: 'Impossible de charger les données.', detailError: 'Détails indisponibles.', activity: 'Activité', artifact: 'Document MD', demo: 'Réponse simulée : le coach pourra comparer cette activité à vos documents lorsque l’inférence sera activée.', syncing: 'Synchronisation Strava…', syncError: 'Synchronisation impossible.', levelError: 'Niveau indisponible.' },
    en: { load: 'Loading…', empty: 'No results.', error: 'Unable to load data.', detailError: 'Details unavailable.', activity: 'Activity', artifact: 'Markdown note', demo: 'Simulated reply: the coach can compare this activity with your documents when inference is enabled.', syncing: 'Syncing Strava…', syncError: 'Sync failed.', levelError: 'Level unavailable.' }
  };
  function open() {
    previousFocus = document.activeElement; overlay.hidden = false; panel.inert = false;
    panel.classList.add('open'); panel.setAttribute('aria-hidden','false'); trigger.setAttribute('aria-expanded','true');
    $('close-settings').focus();
    loadLevel();
    if (!items.length) load();
  }
  function close() {
    panel.classList.remove('open'); panel.setAttribute('aria-hidden','true'); panel.inert = true;
    overlay.hidden = true; trigger.setAttribute('aria-expanded','false'); (previousFocus || trigger).focus();
  }
  trigger.addEventListener('click',open); $('close-settings').addEventListener('click',close); overlay.addEventListener('click',close);
  panel.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const focusable = [...panel.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled])')];
    if (!focusable.length) return;
    if (event.shiftKey && document.activeElement === focusable[0]) { event.preventDefault(); focusable.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0].focus(); }
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { if (dialog.open) dialog.close(); else if (panel.classList.contains('open')) close(); } });
  $('detail-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  $('language').addEventListener('change', event => { lang = event.target.value === 'en' ? 'en' : 'fr'; document.documentElement.lang = lang; render(); });
  $('athlete-profile-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form=event.currentTarget, status=$('profile-status'), field=id=>$(id).value.trim();
    const optionalInteger=value=>value===''?null:Number.parseInt(value,10);
    const weight=field('profile-weight');
    try {
      const response=await fetch('/api/profile',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        weight_kg:weight===''?null:Number.parseFloat(weight), ftp_watts:optionalInteger(field('profile-ftp')),
        max_heartrate:optionalInteger(field('profile-hrmax'))
      })});
      const result=await response.json(); if(!response.ok) throw new Error(result.detail || 'Enregistrement impossible');
      status.textContent='Constantes enregistrées.'; await loadLevel();
    } catch(error) { status.textContent=error.message || 'Enregistrement impossible.'; }
  });
  $('filter').addEventListener('input',render); $('sort').addEventListener('change',render);
  $('chat-form').addEventListener('submit', event => {
    event.preventDefault(); if (busy) return;
    const input=$('chat-input'), text=input.value.trim(); if (!text) return;
    busy=true; addMessage('user',text); input.value=''; input.style.height='auto';
    setTimeout(() => { addMessage('assistant',copy[lang].demo,true); busy=false; },350);
  });
  $('chat-input').addEventListener('input',event => { event.target.style.height='auto'; event.target.style.height=Math.min(event.target.scrollHeight,130)+'px'; });
  $('chat-input').addEventListener('keydown',event => { if (event.key==='Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat-form').requestSubmit(); } });
  if ($('sync-strava')) $('sync-strava').addEventListener('click',syncStrava);

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
  function showLevel(snapshot) {
    const target = $('level-snapshot'); target.replaceChildren();
    const dl = document.createElement('dl'); dl.className='profile';
    const fields = [
      ['Niveau', snapshot.lvl == null ? '—' : `${snapshot.lvl}/100`],
      ['Tendance', snapshot.tr == null ? '—' : `${snapshot.tr > 0 ? '+' : ''}${snapshot.tr}`],
      ['FTP estimé', num(snapshot.ftp,' W')],
      ['FTP relatif', num(snapshot.ftp_wkg,' W/kg')],
      ...Object.entries(snapshot.sc || {}).map(([name,value]) => [name,`${value}/100`]),
    ];
    fields.forEach(([label,value]) => { const wrap=document.createElement('div'), dt=document.createElement('dt'), dd=document.createElement('dd'); dt.textContent=label; dd.textContent=value; wrap.append(dt,dd); dl.appendChild(wrap); });
    const note=document.createElement('p'); note.className='hint'; note.textContent=`Calcul au ${snapshot.asof || '—'} · records de puissance réelle uniquement.`;
    target.append(dl,note);
  }
  async function loadLevel() {
    try { const response=await fetch('/api/level',{credentials:'same-origin'}); if(!response.ok) throw Error(); showLevel(await response.json()); }
    catch (_) { $('level-snapshot').textContent=copy[lang].levelError; }
  }
  async function syncStrava() {
    const button=$('sync-strava'), status=$('sync-status'); if(!button || button.disabled) return;
    button.disabled=true; status.textContent=copy[lang].syncing;
    try {
      const response=await fetch('/api/activities/refresh',{method:'POST',credentials:'same-origin'});
      const result=await response.json(); if(!response.ok) throw new Error(result.detail || copy[lang].syncError);
      status.textContent=`${result.mode === 'initial' ? 'Import initial' : 'Actualisation'} : ${result.imported} activité(s), ${result.compacted} résumé(s) compact(s).`;
      items=[]; await load(); await loadLevel();
    } catch (error) { status.textContent=error.message || copy[lang].syncError; }
    finally { button.disabled=false; }
  }
  async function showCompact(activity, segment=null) {
    const response=await fetch(`/api/activities/${encodeURIComponent(activity.id)}/compact${segment ? `?segment=${encodeURIComponent(segment)}` : ''}`,{credentials:'same-origin'});
    const body=await response.json();
    if(!response.ok) throw new Error(body.detail || copy[lang].detailError);
    const heading=document.createElement('h3'); heading.textContent=segment ? `Résumé compact (${segment})` : 'Résumé compact';
    const count=document.createElement('p'); count.className='hint'; count.textContent=`${response.headers.get('X-Compact-Characters') || JSON.stringify(body).length} caractères JSON`;
    const pre=document.createElement('pre'); pre.className='markdown'; pre.textContent=JSON.stringify(body);
    $('detail-body').append(heading,count,pre);
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
        const compact=document.createElement('button'); compact.textContent='Voir le JSON compact'; compact.addEventListener('click',()=>showCompact(item).catch(error=>{body.append(document.createTextNode(error.message));})); body.appendChild(compact);
        const race=document.createElement('button'); race.textContent='Résumé course · segment continu le plus long'; race.addEventListener('click',()=>showCompact(item,'longest').catch(error=>{body.append(document.createTextNode(error.message));})); body.appendChild(race);
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
  const query=new URLSearchParams(location.search);
  if(query.get('strava')==='connected'){
    history.replaceState({},'',location.pathname);
    open();
    syncStrava(); // first connection imports up to the latest 20 activities
  } else if(query.get('strava')==='refreshed'){
    history.replaceState({},'',location.pathname);
  }
})();
