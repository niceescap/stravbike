/* ═══════════════════════════════════════════════════════════
   CALENDAR.JS — FullCalendar + panneau latéral + commentaires
   Toutes les requêtes API passent par apiFetch() (app.js) qui
   injecte X-API-Key automatiquement.
═══════════════════════════════════════════════════════════ */

let calendar, chartInst, currentEventData;

/* ── Helpers ── */
function eventClass(ev) {
    if (ev.competition_id) return `fc-event-comp-${ev.objective_level || 'C'}`;
    if (ev.session_id) return 'fc-event-session';
    return 'fc-event-activity';
}

function eventTitle(ev) {
    const badge = ev.badge || '';
    if (ev.competition_id) return `🏆 ${ev.competition_name || 'Compétition'}`;
    if (ev.session_id) return `${badge} ${ev.session_title || 'Séance'}`;
    if (ev.activity_id) return `${badge} ${ev.activity_name || 'Sortie'}`;
    return badge;
}

/* ── Init FullCalendar ── */
function initCalendar() {
    const calEl = document.getElementById('calendar');
    if (!calEl) return;
    calendar = new FullCalendar.Calendar(calEl, {
        initialView: 'dayGridMonth',
        locale: 'fr',
        firstDay: 1,
        headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek' },
        dayMaxEvents: 3,
        eventClassNames: info => [eventClass(info.event.extendedProps)],
        events: async (info, ok, fail) => {
            try {
                const start = info.startStr.split('T')[0];
                const data = await apiFetch(`${API}/calendar/week?start_date=${start}`);
                const evs = data.map(ev => ({
                    id: ev.activity_id || ev.session_id || ev.competition_id,
                    title: eventTitle(ev),
                    start: ev.calendar_date,
                    allDay: true,
                    extendedProps: ev
                }));
                _pendingTss = aggregateTss(data);
                ok(evs);
            } catch(e) { fail(e); }
        },
        eventClick: info => { currentEventData = info.event.extendedProps; openPanel(currentEventData); },
        dateClick: info => { openPanelCreate(info.dateStr); },
        datesSet: () => { setTimeout(renderTssBars, 120); }
    });
    calendar.render();
}

/* ── TSS bars ── */
let _pendingTss = {};
function aggregateTss(data) {
    const map = {};
    data.forEach(ev => { if (ev.tss && ev.calendar_date) map[ev.calendar_date] = (map[ev.calendar_date] || 0) + parseFloat(ev.tss); });
    return map;
}

function renderTssBars() {
    const maxTss = 150;
    document.querySelectorAll('.fc-daygrid-day[data-date]').forEach(cell => {
        const date = cell.getAttribute('data-date');
        const tss = _pendingTss[date] || 0;
        cell.querySelector('.tss-bar')?.remove();
        if (tss > 0) {
            const pct = Math.min(tss / maxTss * 100, 100);
            const bar = document.createElement('div');
            bar.className = 'tss-bar';
            bar.style.width = pct + '%';
            bar.title = `TSS : ${Math.round(tss)}`;
            const frame = cell.querySelector('.fc-daygrid-day-frame');
            if (frame) frame.appendChild(bar);
        }
    });
}

/* ── Panneau latéral ── */
function openPanel(ev) {
    let eyebrow, title;
    if (ev.competition_id) { eyebrow = 'Compétition'; title = ev.competition_name || 'Course'; }
    else if (ev.session_id && ev.activity_id) { eyebrow = 'Séance + Activité'; title = ev.session_title || 'Séance'; }
    else if (ev.session_id) { eyebrow = 'Séance planifiée'; title = ev.session_title || 'Séance'; }
    else { eyebrow = 'Activité Strava'; title = ev.activity_name || 'Sortie'; }

    document.getElementById('panel-eyebrow').textContent = eyebrow;
    document.getElementById('panel-title').textContent = title;
    document.getElementById('panel-date').textContent = fmtDate(ev.calendar_date);

    const body = document.getElementById('panel-body');
    body.innerHTML = buildPanelBody(ev);
    body.scrollTop = 0;

    if (ev.activity_id || ev.session_id) loadComments(ev);

    document.getElementById('panel').classList.add('open');
    document.getElementById('panel-overlay').classList.add('show');
}

function buildPanelBody(ev) {
    let html = '';

    if (ev.session_id) {
        const status = ev.session_status || 'planned';
        if (status === 'validated') html += '<div><span class="validation-badge badge-ok">✓ Séance validée</span></div>';
        else if (status === 'missed') html += '<div><span class="validation-badge badge-fail">✗ Séance non effectuée</span></div>';
        else html += '<div><span class="validation-badge badge-wait">⏳ En attente</span></div>';
    }

    if (ev.activity_id) {
        html += `
        <div>
            <div class="panel-section-title">Métriques</div>
            <div class="metrics-grid">
                <div class="metric-card"><div class="metric-value">${ev.tss ? Math.round(ev.tss) : '—'}</div><div class="metric-label">TSS</div></div>
                <div class="metric-card"><div class="metric-value">${ev.intensity_factor ? parseFloat(ev.intensity_factor).toFixed(2) : '—'}</div><div class="metric-label">IF</div></div>
                <div class="metric-card"><div class="metric-value">${ev.moving_time_min ? fmtDuration(ev.moving_time_min) : '—'}</div><div class="metric-label">Durée</div></div>
            </div>
        </div>
        <button class="btn-chart" onclick="viewChart(${ev.activity_id})">📈 Graphique puissance / FC</button>`;
    }

    if (ev.session_id && ev.session_description) {
        html += `<div><div class="panel-section-title">Séance prescrite</div><div class="session-desc">${ev.session_description}</div></div>`;
    }

    if (ev.competition_id) {
        const lvl = ev.objective_level || 'C';
        html += `<div><div class="panel-section-title">Informations</div><div style="display:flex;flex-direction:column;gap:10px"><div><span class="comp-level comp-${lvl}">Objectif ${lvl}</span></div>${ev.result_rank ? `<p style="font-size:13px">🥇 Classement : <b>${ev.result_rank}</b></p>` : ''}</div></div>`;
    }

    if (ev.activity_id || ev.competition_id) {
        html += `<div><div class="panel-section-title">Analyse IA</div><div class="llm-card"><div class="llm-header">● Coach IA</div><span id="llm-text">Cliquez pour générer une analyse…</span><br><br><button class="btn-secondary" style="font-size:12px;padding:6px 12px" onclick="requestLLM(${ev.activity_id || 'null'})">Générer l'analyse</button></div></div>`;
    }

    html += `<div><div class="panel-section-title">Commentaires</div><div id="comments-list" style="display:flex;flex-direction:column;gap:8px"><div class="spinner"></div></div></div>`;

    const entityId = ev.activity_id || ev.session_id;
    const entityType = ev.activity_id ? 'activity' : ev.session_id ? 'session' : null;
    if (entityId && entityType) {
        html += `<div><div class="comment-input-wrap"><textarea id="new-comment" placeholder="Ajouter un commentaire…"></textarea><div class="comment-input-footer"><select class="role-select" id="comment-role"><option value="coach">Coach</option><option value="athlete">Athlète</option></select><button class="btn-send" onclick="addComment(${entityId}, '${entityType}')">Envoyer</button></div></div></div>`;
    }
    return html;
}

function openPanelCreate(dateStr) {
    document.getElementById('panel-eyebrow').textContent = 'Nouveau';
    document.getElementById('panel-title').textContent = 'Ajouter une séance';
    document.getElementById('panel-date').textContent = fmtDate(dateStr);
    document.getElementById('panel-body').innerHTML = buildCreateForm(dateStr);
    document.getElementById('panel').classList.add('open');
    document.getElementById('panel-overlay').classList.add('show');
}

function buildCreateForm(dateStr) {
    return `<div><div class="panel-section-title">Séance planifiée</div><div style="display:flex;flex-direction:column;gap:12px">
        <div class="form-row"><div class="form-label">Date</div><input class="form-input" type="date" id="sess-date" value="${dateStr}"></div>
        <div class="form-row"><div class="form-label">Titre</div><input class="form-input" type="text" id="sess-title" placeholder="ex : Tempo 2×20 min"></div>
        <div class="form-row"><div class="form-label">Description</div><textarea class="form-input" id="sess-desc" rows="4" placeholder="Décrire les objectifs, intervalles, zones de puissance…" style="resize:vertical"></textarea></div>
        <div class="form-row-2">
            <div class="form-row"><div class="form-label">Durée cible (min)</div><input class="form-input" type="number" id="sess-duration" placeholder="90"></div>
            <div class="form-row"><div class="form-label">TSS cible</div><input class="form-input" type="number" id="sess-tss" placeholder="80"></div>
        </div>
        <div class="form-row"><div class="form-label">Type de sport</div><select class="form-input" id="sess-type"><option value="Ride">Vélo</option><option value="VirtualRide">Home-trainer</option><option value="Run">Course à pied</option></select></div>
        <div class="form-actions"><button class="btn-primary" onclick="createSession()">Créer la séance</button><button class="btn-secondary" onclick="closePanel()">Annuler</button></div>
    </div></div>`;
}

function closePanel() {
    document.getElementById('panel').classList.remove('open');
    document.getElementById('panel-overlay').classList.remove('show');
}

/* ── Sessions ── */
async function createSession() {
    const date = document.getElementById('sess-date')?.value;
    const title = document.getElementById('sess-title')?.value?.trim();
    const desc = document.getElementById('sess-desc')?.value;
    const duration = document.getElementById('sess-duration')?.value;
    const tss = document.getElementById('sess-tss')?.value;
    const type = document.getElementById('sess-type')?.value;
    if (!title) { showToast('⚠ Titre requis'); return; }
    try {
        await apiPost(API + '/sessions/', {
            session_date: date, title, description: desc,
            target_duration_min: parseInt(duration) || null,
            target_tss: parseFloat(tss) || null, sport_type: type
        });
        closePanel(); calendar.refetchEvents(); showToast('✓ Séance créée');
    } catch(e) { showToast('Erreur création séance'); }
}

/* ── Commentaires ── */
async function loadComments(ev) {
    const listEl = document.getElementById('comments-list');
    if (!listEl) return;
    let url = `${API}/comments/?`;
    if (ev.activity_id) url += `activity_id=${ev.activity_id}`;
    else if (ev.session_id) url += `session_id=${ev.session_id}`;
    else { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Aucun commentaire.</p>'; return; }
    try {
        const comments = await apiFetch(url);
        if (!comments.length) { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Aucun commentaire.</p>'; return; }
        listEl.innerHTML = comments.map(c => {
            const isCoach = c.author_role === 'coach';
            return `<div class="comment-item"><div class="comment-avatar ${isCoach ? 'avatar-coach' : 'avatar-athlete'}">${isCoach ? 'C' : 'N'}</div><div class="comment-bubble"><div class="comment-meta">${isCoach ? 'Coach' : 'Nicolas'} · ${c.created_at ? new Date(c.created_at).toLocaleDateString('fr-FR') : ''}</div>${c.comment}</div></div>`;
        }).join('');
    } catch(e) { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Erreur chargement.</p>'; }
}

async function addComment(entityId, entityType) {
    const text = document.getElementById('new-comment')?.value?.trim();
    const role = document.getElementById('comment-role')?.value || 'coach';
    if (!text) return;
    try {
        await apiPost(API + '/comments/', {
            activity_id: entityType === 'activity' ? entityId : null,
            session_id: entityType === 'session' ? entityId : null,
            comment: text, author_role: role
        });
        document.getElementById('new-comment').value = '';
        loadComments(currentEventData);
        showToast('✓ Commentaire envoyé');
    } catch(e) { showToast('Erreur envoi commentaire'); }
}

/* ── LLM placeholder (sera remplacé par le chat intégré) ── */
async function requestLLM(activityId) {
    const el = document.getElementById('llm-text');
    if (!el) return;
    el.innerHTML = '<span class="spinner"></span>';
    try {
        const data = await apiPost(API + '/llm/analyze', { activity_id: activityId });
        el.textContent = data.analysis || data.message || 'Analyse générée.';
    } catch(e) { el.textContent = 'Analyse non disponible (endpoint LLM à brancher).'; }
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => { initCalendar(); });
