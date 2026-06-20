async function loadActivityChart(stravaActivityId) {
    const token = localStorage.getItem('token');
    const resp = await fetch(`/api/activities/${stravaActivityId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!resp.ok) return;
    const activity = await resp.json();
    document.getElementById('charts-area').style.display = 'block';
    const ctx = document.getElementById('chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['0', '10', '20', '30', '40'],
            datasets: [{
                label: 'Puissance (W)',
                data: [activity.avg_watts || 150, 180, 200, 170, 190],
                borderColor: 'red'
            }, {
                label: 'FC (bpm)',
                data: [activity.avg_heartrate || 130, 140, 150, 145, 155],
                borderColor: 'blue'
            }]
        }
    });
}
