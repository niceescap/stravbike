let calendar;

function initCalendar() {
    const calendarEl = document.getElementById('calendar');
    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        events: fetchEvents,
        eventClick: handleEventClick,
        locale: 'fr',
        firstDay: 1
    });
    calendar.render();
}

async function fetchEvents(info, successCallback, failureCallback) {
    const startStr = info.startStr;
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
        const response = await fetch(`/api/calendar/week?start_date=${startStr}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Unauthorized');
        const data = await response.json();
        const events = data.map(ev => ({
            id: ev.id || ev.activity_id || ev.session_id,
            title: ev.badge + ' ' + (ev.activity_name || ev.session_title || ev.competition_name || 'Activité'),
            start: ev.calendar_date,
            end: ev.calendar_date,
            backgroundColor: ev.competition_id ? '#F44336' : ev.session_id ? '#FF9800' : '#4CAF50',
            extendedProps: ev
        }));
        successCallback(events);
    } catch (err) {
        failureCallback(err);
    }
}

function handleEventClick(info) {
    const props = info.event.extendedProps;
    document.getElementById('panel-content').innerHTML = renderPanel(props);
}
