function renderPanel(props) {
    let html = '';
    if (props.activity_id) {
        html = `<h4>Activité</h4>
                <p>Nom: ${props.activity_name || ''}</p>
                <p>TSS: ${props.tss || '-'}</p>
                <p>IF: ${props.intensity_factor || '-'}</p>`;
    } else if (props.session_id) {
        html = `<h4>Séance planifiée</h4>
                <p>Titre: ${props.session_title || ''}</p>
                <p>Statut: ${props.session_status || ''}</p>`;
    } else if (props.competition_id) {
        html = `<h4>Compétition</h4>
                <p>Nom: ${props.competition_name || ''}</p>
                <p>Niveau: ${props.objective_level || ''}</p>`;
    }
    return html;
}
