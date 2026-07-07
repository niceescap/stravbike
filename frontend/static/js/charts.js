/* ═══════════════════════════════════════════════════════════
   CHARTS.JS — Chart.js pour graphiques puissance / FC
   TODO: brancher sur vrais streams quand /api/activities/{id}/streams
         sera implémenté (récupération streams Strava à l'ingestion).
═══════════════════════════════════════════════════════════ */

function viewChart(activityId) {
    const modal = document.getElementById('chart-modal');
    if (!modal) return;
    modal.classList.add('open');
    const ctx = document.getElementById('chart-canvas').getContext('2d');
    if (chartInst) chartInst.destroy();

    // Données mock (sera remplacé par fetch streams)
    const labels = Array.from({ length: 20 }, (_, i) => `${i * 5} min`);
    const watts = labels.map(() => 180 + Math.round((Math.random() - .5) * 80));
    const hr = labels.map(() => 148 + Math.round((Math.random() - .5) * 20));

    chartInst = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Puissance (W)', data: watts, borderColor: '#FF6B35', backgroundColor: '#FF6B3518', fill: true, tension: .4, pointRadius: 0, borderWidth: 2, yAxisID: 'yW' },
                { label: 'FC (bpm)', data: hr, borderColor: '#00D4AA', backgroundColor: 'transparent', fill: false, tension: .4, pointRadius: 0, borderWidth: 2, yAxisID: 'yHR' }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: '#7A8099', font: { family: 'Inter', size: 11 } } } },
            scales: {
                x:   { ticks: { color: '#7A8099', font: { size: 10 } }, grid: { color: '#2A3045' } },
                yW:  { position: 'left',  ticks: { color: '#FF6B35', font: { size: 10 } }, grid: { color: '#2A304555' } },
                yHR: { position: 'right', ticks: { color: '#00D4AA', font: { size: 10 } }, grid: { display: false } }
            }
        }
    });
}

function closeChart() {
    const modal = document.getElementById('chart-modal');
    if (modal) modal.classList.remove('open');
}
