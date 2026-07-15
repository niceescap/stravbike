/* ═══════════════════════════════════════════════════════════
   calendar.js — FullCalendar + panneau latéral + TSS bars
   Logique extraite du prototype V3, auth via App.SERVICE_KEY
   ═══════════════════════════════════════════════════════════ */

const Calendar = {
    calendar: null,
    currentEventData: null,
    _pendingTss: {},

    init() {
        const calEl = document.getElementById('calendar');
        if (!calEl) return;

        this.calendar = new FullCalendar.Calendar(calEl, {
            initialView: 'dayGridMonth',
            locale: 'fr',
            firstDay: 1,
            headerToolbar: {
                left:   'prev,next today',
                center: 'title',
                right:  'dayGridMonth,timeGridWeek',
            },
            dayMaxEvents: 3,
            eventClassNames: info => [this._eventClass(info.event.extendedProps)],
            events: async (info, ok, fail) => {
                try {
                    const start = info.startStr.split('T')[0];
                    const end = info.endStr.split('T')[0];
                    const data = await App.apiFetch(`${App.API}/calendar/week?start_date=${start}&end_date=${end}`);
                    this._pendingTss = this._aggregateTss(data);
                    ok(data.map(ev => ({
                        id: ev.activity_id || ev.session_id || ev.competition_id,
                        title: this._eventTitle(ev),
                        start: ev.calendar_date,
                        allDay: true,
                        extendedProps: ev,
                    })));
                } catch (e) { fail(e); }
            },
            eventClick: info => {
                this.currentEventData = info.event.extendedProps;
                this.openPanel(this.currentEventData);
            },
            dateClick: info => {
                this.openPanelCreate(info.dateStr);
            },
            datesSet: () => {
                setTimeout(() => this._renderTssBars(), 120);
            },
        });
        this.calendar.render();
    },

    // ── Helpers événements ──────────────────────────────────
    _eventClass(ev) {
        if (ev.competition_id) return `fc-event-comp-${ev.objective_level || 'C'}`;
        if (ev.session_id)     return 'fc-event-session';
        return 'fc-event-activity';
    },

    _eventTitle(ev) {
        const badge = ev.badge || '';
        if (ev.competition_id) return `🏆 ${ev.competition_name || 'Compétition'}`;
        if (ev.session_id)     return `${badge} ${ev.session_title || 'Séance'}`;
        if (ev.activity_id)    return `${badge} ${ev.activity_name || 'Sortie'}`;
        return badge;
    },

    _aggregateTss(data) {
        const map = {};
        data.forEach(ev => {
            if (ev.tss && ev.calendar_date) {
                map[ev.calendar_date] = (map[ev.calendar_date] || 0) + parseFloat(ev.tss);
            }
        });
        return map;
    },

    _renderTssBars() {
        const maxTss = 150;
        document.querySelectorAll('.fc-daygrid-day[data-date]').forEach(cell => {
            const date = cell.getAttribute('data-date');
            const tss = this._pendingTss[date] || 0;
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
    },

    // ── Panneau latéral ─────────────────────────────────────
    openPanel(ev) {
        let eyebrow, title;
        if (ev.competition_id)                         { eyebrow = 'Compétition';       title = ev.competition_name || 'Course'; }
        else if (ev.session_id && ev.activity_id)      { eyebrow = 'Séance + Activité'; title = ev.session_title || 'Séance'; }
        else if (ev.session_id)                        { eyebrow = 'Séance planifiée';  title = ev.session_title || 'Séance'; }
        else                                           { eyebrow = 'Activité Strava';   title = ev.activity_name || 'Sortie'; }

        document.getElementById('panel-eyebrow').textContent = eyebrow;
        document.getElementById('panel-title').textContent   = title;
        document.getElementById('panel-date').textContent    = App.fmtDate(ev.calendar_date);

        const body = document.getElementById('panel-body');
        body.innerHTML = this._buildPanelBody(ev);
        body.scrollTop = 0;

        if (ev.activity_id || ev.session_id) this._loadComments(ev);

        document.getElementById('panel').classList.add('open');
        document.getElementById('panel-overlay').classList.add('show');
    },

    _buildPanelBody(ev) {
        let html = '';

        // Badge validation
        if (ev.session_id) {
            const status = ev.session_status || 'planned';
            const cls = status === 'validated' ? 'badge-ok' : status === 'missed' ? 'badge-fail' : 'badge-wait';
            const txt = status === 'validated' ? '✓ Séance validée' : status === 'missed' ? '✗ Séance non effectuée' : '⏳ En attente';
            html += `<div><span class="validation-badge ${cls}">${txt}</span></div>`;
        }

        // Métriques activité
        if (ev.activity_id) {
            html += `
            <div>
                <div class="panel-section-title">Métriques</div>
                <div class="metrics-grid">
                    <div class="metric-card"><div class="metric-value">${ev.tss ? Math.round(ev.tss) : '—'}</div><div class="metric-label">TSS</div></div>
                    <div class="metric-card"><div class="metric-value">${ev.intensity_factor ? parseFloat(ev.intensity_factor).toFixed(2) : '—'}</div><div class="metric-label">IF</div></div>
                    <div class="metric-card"><div class="metric-value">${ev.moving_time_min ? App.fmtDuration(ev.moving_time_min) : '—'}</div><div class="metric-label">Durée</div></div>
                    <div class="metric-card"><div class="metric-value">${ev.distance_km ? Math.round(ev.distance_km) : '—'}</div><div class="metric-label">km</div></div>
                    <div class="metric-card"><div class="metric-value">${ev.avg_heartrate ? Math.round(ev.avg_heartrate) : '—'}</div><div class="metric-label">FC moy</div></div>
                    <div class="metric-card"><div class="metric-value">${ev.avg_speed_kmh ? parseFloat(ev.avg_speed_kmh).toFixed(1) : '—'}</div><div class="metric-label">km/h</div></div>
                </div>
            </div>`;
        }

        // Description séance
        if (ev.session_id && ev.session_description) {
            html += `<div><div class="panel-section-title">Séance prescrite</div><div class="session-desc">${ev.session_description}</div></div>`;
        }

        // Compétition
        if (ev.competition_id) {
            const lvl = ev.objective_level || 'C';
            html += `<div><div class="panel-section-title">Informations</div><div style="display:flex;flex-direction:column;gap:10px">
                <div><span class="comp-level comp-${lvl}">Objectif ${lvl}</span></div>
                ${ev.result_rank ? `<p style="font-size:13px">🥇 Classement : <b>${ev.result_rank}</b></p>` : ''}
            </div></div>`;
        }

        // Commentaires
        html += `<div><div class="panel-section-title">Commentaires</div><div id="comments-list" style="display:flex;flex-direction:column;gap:8px"><div class="spinner"></div></div></div>`;

        const entityId = ev.activity_id || ev.session_id;
        const entityType = ev.activity_id ? 'activity' : ev.session_id ? 'session' : null;
        if (entityId && entityType) {
            html += `<div><div class="comment-input-wrap">
                <textarea id="new-comment" placeholder="Ajouter un commentaire…"></textarea>
                <div class="comment-input-footer">
                    <select class="role-select" id="comment-role"><option value="visiteur" selected>Visiteur</option><option value="athlète">Athlète</option></select>
                    <button class="btn-send" onclick="Calendar._addComment(${entityId}, '${entityType}')">Envoyer</button>
                </div>
            </div></div>`;
        }

        // Lien vers la page de détail complète
        if (ev.activity_id) {
            html += `<div style="margin-top:8px"><a href="/activities/${ev.activity_id}" class="btn-detail-link">📊 Voir le détail complet & graphique →</a></div>`;
        }

        return html;
    },

    openPanelCreate(dateStr) {
        document.getElementById('panel-eyebrow').textContent = 'Nouveau';
        document.getElementById('panel-title').textContent   = 'Ajouter une séance';
        document.getElementById('panel-date').textContent    = App.fmtDate(dateStr);
        document.getElementById('panel-body').innerHTML = this._buildCreateForm(dateStr);
        document.getElementById('panel').classList.add('open');
        document.getElementById('panel-overlay').classList.add('show');
    },

    _buildCreateForm(dateStr) {
        return `
        <div>
            <div class="panel-section-title">Séance planifiée</div>
            <div style="display:flex;flex-direction:column;gap:12px">
                <div class="form-row"><div class="form-label">Date</div><input class="form-input" type="date" id="sess-date" value="${dateStr}"></div>
                <div class="form-row"><div class="form-label">Titre</div><input class="form-input" type="text" id="sess-title" placeholder="ex : Tempo 2×20 min"></div>
                <div class="form-row"><div class="form-label">Description</div><textarea class="form-input" id="sess-desc" rows="4" placeholder="Décrire les objectifs, intervalles, zones…" style="resize:vertical"></textarea></div>
                <div class="form-row-2">
                    <div class="form-row"><div class="form-label">Durée (min)</div><input class="form-input" type="number" id="sess-duration" placeholder="90"></div>
                    <div class="form-row"><div class="form-label">Type</div><select class="form-input" id="sess-type"><option value="Ride">Vélo</option><option value="VirtualRide">Home-trainer</option><option value="Run">Course à pied</option></select></div>
                </div>
                <div class="form-actions">
                    <button class="btn-primary" onclick="Calendar._createSession()">Créer la séance</button>
                    <button class="btn-secondary" onclick="Calendar.closePanel()">Annuler</button>
                </div>
            </div>
        </div>`;
    },

    closePanel() {
        document.getElementById('panel').classList.remove('open');
        document.getElementById('panel-overlay').classList.remove('show');
    },

    // ── Création séance ─────────────────────────────────────
    async _createSession() {
        const date     = document.getElementById('sess-date')?.value;
        const title    = document.getElementById('sess-title')?.value?.trim();
        const desc     = document.getElementById('sess-desc')?.value;
        const duration = document.getElementById('sess-duration')?.value;
        const type     = document.getElementById('sess-type')?.value;
        if (!title) { App.showToast('⚠ Titre requis'); return; }

        try {
            await App.apiFetch(`${App.API}/sessions/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_date: date, title, description: desc,
                    target_duration_min: parseInt(duration) || null, sport_type: type,
                }),
            });
            this.closePanel();
            this.calendar.refetchEvents();
            App.showToast('✓ Séance créée');
        } catch (e) { App.showToast('Erreur création séance'); }
    },

    // ── Commentaires ────────────────────────────────────────
    async _loadComments(ev) {
        const listEl = document.getElementById('comments-list');
        if (!listEl) return;
        let url = `${App.API}/comments/?`;
        if (ev.activity_id) url += `activity_id=${ev.activity_id}`;
        else if (ev.session_id) url += `session_id=${ev.session_id}`;
        else { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Aucun commentaire.</p>'; return; }

        try {
            const comments = await App.apiFetch(url);
            if (!comments.length) { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Aucun commentaire.</p>'; return; }
            listEl.innerHTML = comments.map(c => {
                const isCoach = c.author_role === 'coach';
                return `<div class="comment-item">
                    <div class="comment-avatar ${isCoach ? 'avatar-coach' : 'avatar-athlete'}">${isCoach ? 'C' : 'N'}</div>
                    <div class="comment-bubble">
                        <div class="comment-meta">${isCoach ? 'Coach' : 'Nicolas'} · ${c.created_at ? new Date(c.created_at).toLocaleDateString('fr-FR') : ''}</div>
                        ${c.comment}
                    </div>
                </div>`;
            }).join('');
        } catch (e) { listEl.innerHTML = '<p style="color:var(--muted);font-size:12px">Erreur chargement.</p>'; }
    },

    async _addComment(entityId, entityType) {
        const text = document.getElementById('new-comment')?.value?.trim();
        const role = document.getElementById('comment-role')?.value || 'coach';
        if (!text) return;
        try {
            await App.apiFetch(`${App.API}/comments/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    activity_id: entityType === 'activity' ? entityId : null,
                    session_id:  entityType === 'session'  ? entityId : null,
                    comment: text, author_role: role,
                }),
            });
            document.getElementById('new-comment').value = '';
            this._loadComments(this.currentEventData);
            App.showToast('✓ Commentaire envoyé');
        } catch (e) { App.showToast('Erreur envoi commentaire'); }
    },
};
