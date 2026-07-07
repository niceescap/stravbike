#!/bin/bash
set -e

FILES="api/routes/activities.py api/routes/competitions.py api/routes/sessions.py api/routes/calendar.py api/routes/llm.py api/routes/comments.py"

echo "=== Sauvegarde ==="
for f in $FILES; do
    if [ -f "$f" ]; then
        cp "$f" "$f.bak"
        echo "Backup: $f.bak"
    else
        echo "ATTENTION: $f introuvable, ignoré"
    fi
done

echo ""
echo "=== Modification ==="
for f in $FILES; do
    [ -f "$f" ] || continue
    sed -i '/from api.routes.auth import get_current_coach/d' "$f"
    sed -i 's/, *coach *= *Depends(get_current_coach)//' "$f"
    sed -i 's/coach *= *Depends(get_current_coach), *//' "$f"
    sed -i 's/coach *= *Depends(get_current_coach)//' "$f"
    echo "Modifié: $f"
done

echo ""
echo "=== Diff pour vérification ==="
for f in $FILES; do
    [ -f "$f.bak" ] || continue
    echo "--- $f ---"
    diff "$f.bak" "$f" || true
    echo ""
done

echo "Terminé. Vérifie les diffs ci-dessus."
echo "Si tout est correct : rm api/routes/*.bak"
echo "Si un fichier a un problème : cp api/routes/<fichier>.bak api/routes/<fichier>"
