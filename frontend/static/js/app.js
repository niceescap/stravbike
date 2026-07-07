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
    async refreshActivities() {
        const syncIcon = document.getElementById('sync-icon');
        const syncLabel = document.getElementById('sync-label');
        try {
            this.showToast('↻ Synchronisation…');
            if (syncIcon) syncIcon.classList.add('spinning');
            if (syncLabel) syncLabel.textContent = '…';
            await this.apiFetch(`${this.API}/activities/refresh`, { method: 'POST' });
            if (syncIcon) syncIcon.classList.remove('spinning');
            if (syncLabel) syncLabel.textContent = 'Sync';
            this.showToast('✓ Activités synchronisées');
            if (typeof Calendar !== 'undefined' && Calendar.calendar) {
                Calendar.calendar.refetchEvents();
            }
            if (document.body.dataset.page === 'activities') {
                this.loadActivities();
            }
        } catch (e) {
            if (syncIcon) syncIcon.classList.remove('spinning');
            if (syncLabel) syncLabel.textContent = 'Sync';
            this.showToast('Erreur synchronisation');
        }
    },

    // ── Activities list page ───────────────────────────────
    async loadActivities() {
        const container = document.getElementById('activities-container');
        if (!container) return;
        container.innerHTML = '<div class="spinner"></div>';
        try {
            const activities = await this.apiFetch(`${this.API}/activities/?limit=50`);
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
                ${a.streams_json ? `
                <button class="btn-chart" onclick="Charts.open(${a.id})">
                    📈 Graphique puissance / FC
                </button>` : ''}
            `;
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="color:var(--red)">Erreur de chargement.</div>';
        }
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
