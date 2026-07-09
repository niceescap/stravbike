/* ═══════════════════════════════════════════════════════════
   app.js — Core : auth, utils, nav, athlete, sync
   Service key lue depuis <meta name="api-key"> (injectée par Jinja2)
   ═══════════════════════════════════════════════════════════ */

const App = {
    SERVICE_KEY: '',
    API: '/api',

    init() {
        this.SERVICE_KEY = document.querySelector('meta[name="api-key"]')?.content || '';
        this.markActiveNav();
        this.loadAthleteInfo();

        const page = document.body.dataset.page;
        if (page === 'calendar' && typeof Calendar !== 'undefined') Calendar.init();
        if (page === 'chat' && typeof Chat !== 'undefined') Chat.init();
        if (page === 'activities') this.loadActivities();
        if (page === 'activity_detail') this.loadActivityDetail();
        if (page === 'profile') this.loadProfile();

        // Auto-sync Strava au chargement du calendrier (silencieux, en arrière-plan)
        if (page === 'calendar') this.refreshActivities(true);
    },

    // ── API helpers ────────────────────────────────────────
    async apiFetch(url, opts = {}) {
        const res = await fetch(url, {
            ...opts,
            headers: { ...opts.headers, 'X-API-Key': this.SERVICE_KEY },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },

    // ── Utils ──────────────────────────────────────────────
    showToast(msg, duration = 2500) {
        const t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg;
        t.classList.add('show');
        setTimeout(() => t.classList.remove('show'), duration);
    },

    fmtDate(d) {
        if (!d) return '—';
        return new Date(d).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
    },

    fmtDuration(min) {
        if (!min) return '—';
        const h = Math.floor(min / 60), m = Math.round(min % 60);
        return h ? `${h}h${m.toString().padStart(2, '0')}` : `${m} min`;
    },

    // ── Nav ────────────────────────────────────────────────
    markActiveNav() {
        const page = document.body.dataset.page;
        document.querySelectorAll('.nav-link').forEach(link => {
            if (link.dataset.page === page) link.classList.add('active');
        });
    },

    // ── Athlete ────────────────────────────────────────────
    async loadAthleteInfo() {
        try {
            const data = await this.apiFetch(`${this.API}/athlete`);
            const fn = data.firstname || '', ln = data.lastname || '';
            const nameEl = document.getElementById('athlete-name-text');
            const initialsEl = document.getElementById('athlete-initials');
            const badgeEl = document.getElementById('athlete-badge');
            if (nameEl) nameEl.textContent = `${fn} ${ln}`;
            if (initialsEl) initialsEl.textContent = (fn[0] || '') + (ln[0] || '');
            if (badgeEl) badgeEl.style.display = 'flex';
        } catch (e) { /* silencieux au démarrage */ }
    },

    // ── Sync Strava ────────────────────────────────────────
    async refreshActivities(silent = false) {
        try {
            if (!silent) this.showToast('↻ Synchronisation…');
            await this.apiFetch(`${this.API}/activities/refresh`, { method: 'POST' });
            if (!silent) this.showToast('✓ Activités synchronisées');
            if (typeof Calendar !== 'undefined' && Calendar.calendar) {
                Calendar.calendar.refetchEvents();
            }
            if (document.body.dataset.page === 'activities') {
                this.loadActivities();
            }
        } catch (e) {
            if (!silent) this.showToast('Erreur synchronisation');
        }
    },

    // ── Activities list page ───────────────────────────────
    async loadActivities() {
        const container = document.getElementById('activities-container');
        if (!container) return;
        container.innerHTML = '<div class="spinner"></div>';
        try {
            const activities = await this.apiFetch(`${this.API}/activities/?limit=500`);
            if (!activities.length) {
                container.innerHTML = '<div class="empty-state">Aucune activité. Cliquez sur <strong>Sync</strong> pour importer depuis Strava.</div>';
                return;
            }
            container.innerHTML = activities.map(a => `
                <a class="activity-card" href="/activities/${a.id}">
                    <div class="activity-info">
                        <div class="activity-name">${a.name || 'Sortie'}</div>
                        <div class="activity-date">${a.start_date_local ? new Date(a.start_date_local).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</div>
                    </div>
                    <div class="activity-metrics">
                        <div class="activity-metric"><div class="val">${a.tss ? Math.round(a.tss) : '—'}</div><div class="lbl">TSS</div></div>
                        <div class="activity-metric"><div class="val">${a.intensity_factor ? parseFloat(a.intensity_factor).toFixed(2) : '—'}</div><div class="lbl">IF</div></div>
                        <div class="activity-metric"><div class="val">${a.distance_km ? Math.round(a.distance_km) : '—'}</div><div class="lbl">km</div></div>
                        <div class="activity-metric"><div class="val">${a.moving_time_min ? this.fmtDuration(a.moving_time_min) : '—'}</div><div class="lbl">Durée</div></div>
                    </div>
                </a>
            `).join('');
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--red)">Erreur de chargement.</div>';
        }
    },

    // ── Activity detail page ───────────────────────────────
    async loadActivityDetail() {
        const container = document.getElementById('detail-container');
        if (!container) return;
        const id = container.dataset.activityId;
        container.innerHTML = '<div class="spinner"></div>';
        try {
            const a = await this.apiFetch(`${this.API}/activities/${id}`);

            // Fetch comments en parallèle
            let comments = [];
            try {
                comments = await this.apiFetch(`${this.API}/comments/?activity_id=${id}`);
            } catch (e) { /* comments optionnels */ }

            container.innerHTML = `
                <a href="/activities" class="back-link">← Retour à la liste</a>
                <div class="detail-header">
                    <h1>${a.name || 'Sortie'}</h1>
                    <div class="date">${a.start_date_local ? new Date(a.start_date_local).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</div>
                </div>
                <div class="detail-metrics">
                    <div class="detail-metric"><div class="val">${a.tss ? Math.round(a.tss) : '—'}</div><div class="lbl">TSS</div></div>
                    <div class="detail-metric"><div class="val">${a.intensity_factor ? parseFloat(a.intensity_factor).toFixed(2) : '—'}</div><div class="lbl">IF</div></div>
                    <div class="detail-metric"><div class="val">${a.distance_km ? Math.round(a.distance_km) : '—'}</div><div class="lbl">km</div></div>
                    <div class="detail-metric"><div class="val">${a.moving_time_min ? this.fmtDuration(a.moving_time_min) : '—'}</div><div class="lbl">Durée</div></div>
                    <div class="detail-metric"><div class="val">${a.weighted_avg_watts ? Math.round(a.weighted_avg_watts) : '—'}</div><div class="lbl">NP (W)</div></div>
                    <div class="detail-metric"><div class="val">${a.avg_watts ? Math.round(a.avg_watts) : '—'}</div><div class="lbl">P moy (W)</div></div>
                    <div class="detail-metric"><div class="val">${a.avg_heartrate ? Math.round(a.avg_heartrate) : '—'}</div><div class="lbl">FC moy</div></div>
                    <div class="detail-metric"><div class="val">${a.avg_speed_kmh ? parseFloat(a.avg_speed_kmh).toFixed(1) : '—'}</div><div class="lbl">km/h</div></div>
                </div>

                <button class="btn-chart" onclick="Charts.open(${a.id})">
                    📈 Graphique puissance / FC
                </button>

                <div class="detail-section">
                    <h3>💬 Commentaires</h3>
                    <div id="comments-list" class="comments-list">
                        ${this._renderComments(comments)}
                    </div>
                    <div class="comment-input-wrap">
                        <textarea id="new-comment" placeholder="Ajouter un commentaire…"></textarea>
                        <div class="comment-input-footer">
                            <select class="role-select" id="comment-role"><option value="coach">Coach</option><option value="athlete">Athlète</option></select>
                            <button class="btn-send" onclick="App._addCommentDetail(${a.id})">Envoyer</button>
                        </div>
                    </div>
                </div>
            `;
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--red)">Erreur de chargement.</div>';
        }
    },

    _renderComments(comments) {
        if (!comments || !comments.length) {
            return '<p style="color:var(--muted);font-size:13px">Aucun commentaire.</p>';
        }
        return comments.map(c => {
            const isCoach = c.author_role === 'coach';
            return `<div class="comment-item">
                <div class="comment-avatar ${isCoach ? 'avatar-coach' : 'avatar-athlete'}">${isCoach ? 'C' : 'N'}</div>
                <div class="comment-bubble">
                    <div class="comment-meta">${isCoach ? 'Coach' : 'Nicolas'} · ${c.created_at ? new Date(c.created_at).toLocaleDateString('fr-FR') : ''}</div>
                    ${c.comment}
                </div>
            </div>`;
        }).join('');
    },

    async _addCommentDetail(activityId) {
        const text = document.getElementById('new-comment')?.value?.trim();
        const role = document.getElementById('comment-role')?.value || 'coach';
        if (!text) return;
        try {
            await this.apiFetch(`${this.API}/comments/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    activity_id: activityId,
                    comment: text, author_role: role,
                }),
            });
            document.getElementById('new-comment').value = '';
            // Recharger les commentaires
            const comments = await this.apiFetch(`${this.API}/comments/?activity_id=${activityId}`);
            const listEl = document.getElementById('comments-list');
            if (listEl) listEl.innerHTML = this._renderComments(comments);
            this.showToast('✓ Commentaire envoyé');
        } catch (e) { this.showToast('Erreur envoi commentaire'); }
    },

    // ── Profile page ───────────────────────────────────────
    async loadProfile() {
        const container = document.getElementById('profile-container');
        if (!container) return;
        container.innerHTML = '<div class="spinner"></div>';
        try {
            const a = await this.apiFetch(`${this.API}/athlete`);
            const zonesHtml = (zones, label) => zones && zones.length ? `
                <div class="profile-section">
                    <h3>${label}</h3>
                    ${zones.map((z, i) => `<div class="profile-row"><span class="label">Zone ${i + 1}</span><span class="value">${z.min} – ${z.max}</span></div>`).join('')}
                </div>` : '';

            container.innerHTML = `
                <div class="profile-section">
                    <h3>Identité</h3>
                    <div class="profile-row"><span class="label">Nom</span><span class="value">${a.firstname || ''} ${a.lastname || ''}</span></div>
                    <div class="profile-row"><span class="label">Strava ID</span><span class="value">${a.strava_id || '—'}</span></div>
                </div>
                <div class="profile-section">
                    <h3>Paramètres d'entraînement</h3>
                    <div class="profile-row"><span class="label">FTP</span><span class="value">${a.ftp_watts || '—'} W</span></div>
                    <div class="profile-row"><span class="label">Poids</span><span class="value">${a.weight_kg || '—'} kg</span></div>
                </div>
                <div class="profile-section">
                    <h3>Statistiques (YTD)</h3>
                    <div class="profile-row"><span class="label">Distance</span><span class="value">${a.ytd_distance_km ? Math.round(a.ytd_distance_km) : '—'} km</span></div>
                    <div class="profile-row"><span class="label">Dénivelé</span><span class="value">${a.ytd_elevation_m || '—'} m</span></div>
                    <div class="profile-row"><span class="label">Temps</span><span class="value">${a.ytd_time_hours ? Math.round(a.ytd_time_hours) : '—'} h</span></div>
                </div>
                ${zonesHtml(a.power_zones, 'Zones de puissance (W)')}
                ${zonesHtml(a.heart_rate_zones, 'Zones cardiaques (bpm)')}
            `;
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--red)">Erreur de chargement.</div>';
        }
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
