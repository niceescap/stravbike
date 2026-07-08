/* ═══════════════════════════════════════════════════════════
   charts.js — Modal graphique puissance / FC / vitesse
   Utilise Chart.js. Données depuis GET /api/activities/{id}/streams
   Fetch à la demande : si streams_json en DB → direct, sinon → Strava
   ═══════════════════════════════════════════════════════════ */

const Charts = {
    chartInst: null,

    async open(activityId) {
        const modal = document.getElementById('chart-modal');
        if (!modal) return;
        modal.classList.add('open');

        const ctx = document.getElementById('chart-canvas').getContext('2d');
        if (this.chartInst) this.chartInst.destroy();

        // Afficher un spinner pendant le chargement
        this.chartInst = new Chart(ctx, {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: {
                responsive: true,
                plugins: { title: { display: true, text: 'Chargement des données…', color: '#7A8099' } },
            },
        });

        try {
            const streams = await App.apiFetch(`${App.API}/activities/${activityId}/streams`);
            this._renderChart(ctx, streams);
        } catch (e) {
            if (this.chartInst) this.chartInst.destroy();
            this.chartInst = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [] },
                options: {
                    responsive: true,
                    plugins: { title: { display: true, text: `Erreur: ${e.message}`, color: '#FF4560' } },
                },
            });
        }
    },

    _renderChart(ctx, streams) {
        // Axe X : temps en minutes (fallback : index)
        const labels = streams.time_min || streams.time || Array.from(
            { length: (streams.watts || streams.heartrate || []).length },
            (_, i) => i
        );

        const datasets = [];

        // Puissance
        if (streams.watts && streams.watts.length) {
            datasets.push({
                label: 'Puissance (W)',
                data: streams.watts,
                borderColor: '#FF6B35',
                backgroundColor: '#FF6B3518',
                fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
                yAxisID: 'yW',
            });
        }

        // Fréquence cardiaque
        if (streams.heartrate && streams.heartrate.length) {
            datasets.push({
                label: 'FC (bpm)',
                data: streams.heartrate,
                borderColor: '#00D4AA',
                backgroundColor: 'transparent',
                fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                yAxisID: 'yHR',
            });
        }

        // Vitesse
        if (streams.velocity_smooth && streams.velocity_smooth.length) {
            // Convertir m/s → km/h
            const speedKmh = streams.velocity_smooth.map(v => v * 3.6);
            datasets.push({
                label: 'Vitesse (km/h)',
                data: speedKmh,
                borderColor: '#FFB020',
                backgroundColor: 'transparent',
                fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                yAxisID: 'ySpeed',
                hidden: true,  // caché par défaut (trop chargé)
            });
        }

        // Cadence
        if (streams.cadence && streams.cadence.length) {
            datasets.push({
                label: 'Cadence (rpm)',
                data: streams.cadence,
                borderColor: '#7A8099',
                backgroundColor: 'transparent',
                fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                yAxisID: 'yCadence',
                hidden: true,
            });
        }

        if (this.chartInst) this.chartInst.destroy();

        const scales = {
            x: { ticks: { color: '#7A8099', font: { size: 10 } }, grid: { color: '#2A3045' },
                 title: { display: true, text: 'Temps (min)', color: '#7A8099' } },
        };

        // Ajouter les axes Y dynamiquement selon les datasets
        if (streams.watts) {
            scales.yW = { position: 'left', ticks: { color: '#FF6B35', font: { size: 10 } },
                          grid: { color: '#2A304555' }, title: { display: true, text: 'Watts', color: '#FF6B35' } };
        }
        if (streams.heartrate) {
            scales.yHR = { position: 'right', ticks: { color: '#00D4AA', font: { size: 10 } },
                           grid: { display: false }, title: { display: true, text: 'bpm', color: '#00D4AA' } };
        }
        if (streams.velocity_smooth) {
            scales.ySpeed = { position: 'right', ticks: { color: '#FFB020', font: { size: 10 } },
                              grid: { display: false }, title: { display: true, text: 'km/h', color: '#FFB020' } };
        }
        if (streams.cadence) {
            scales.yCadence = { position: 'right', ticks: { color: '#7A8099', font: { size: 10 } },
                                grid: { display: false }, title: { display: true, text: 'rpm', color: '#7A8099' } };
        }

        this.chartInst = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#7A8099', font: { family: 'Inter', size: 11 } } },
                    tooltip: {
                        callbacks: {
                            title: (items) => `Temps: ${parseFloat(items[0].label).toFixed(1)} min`,
                        },
                    },
                },
                scales,
            },
        });
    },

    close() {
        document.getElementById('chart-modal')?.classList.remove('open');
        if (this.chartInst) { this.chartInst.destroy(); this.chartInst = null; }
    },
};
