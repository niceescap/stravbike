/* ═══════════════════════════════════════════════════════════
   APP.JS — Utils, auth X-API-Key, navigation, shared logic
   Le frontend utilise X-API-Key (même auth que l'outil OpenWebUI).
   La service key est injectée côté serveur via <meta name="api-key">.
═══════════════════════════════════════════════════════════ */

const API = '/api';

/* ── Service key (injectée par Jinja2) ── */
function getServiceKey() {
    return document.querySelector('meta[name="api-key"]')?.content || '';
}

/* ── API helpers ── */
async function apiFetch(url, opts = {}) {
    const key = getServiceKey();
    const headers = { ...opts.headers };
    if (key) headers['X-API-Key'] = key;
    const res = await fetch(url, { ...opts, headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

async function apiPost(url, body) {
    return apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
}

async function apiPut(url, body) {
    return apiFetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
}

async function apiDelete(url) {
    return apiFetch(url, { method: 'DELETE' });
}

/* ── Toast ── */
function showToast(msg, duration = 2500) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), duration);
}

/* ── Formatters ── */
function fmtDate(d) {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
}

function fmtDuration(min) {
    if (!min) return '—';
    const h = Math.floor(min / 60), m = Math.round(min % 60);
    return h ? `${h}h${m.toString().padStart(2,'0')}` : `${m} min`;
}

function fmtDateTime(d) {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/* ── Athlete info (chargé sur toutes les pages) ── */
async function loadAthleteInfo() {
    try {
        const data = await apiFetch(API + '/athlete');
        const fn = data.firstname || '', ln = data.lastname || '';
        const nameEl = document.getElementById('athlete-name-text');
        const initialsEl = document.getElementById('athlete-initials');
        const badgeEl = document.getElementById('athlete-badge');
        if (nameEl) nameEl.textContent = `${fn} ${ln}`;
        if (initialsEl) initialsEl.textContent = (fn[0] || '') + (ln[0] || '');
        if (badgeEl) badgeEl.style.display = 'flex';
    } catch(e) {}
}

/* ── Refresh Strava (bouton header, disponible partout) ── */
async function refreshActivities() {
    try {
        showToast('↻ Synchronisation…');
        await apiPost(API + '/activities/refresh', {});
        showToast('✓ Activités synchronisées');
        if (typeof calendar !== 'undefined' && calendar) calendar.refetchEvents();
        if (typeof loadActivities === 'function') loadActivities();
    } catch(e) { showToast('Erreur synchronisation'); }
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
    loadAthleteInfo();
});
