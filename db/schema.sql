-- =============================================================================
-- SCHEMA PostgreSQL — Application Strava Coach
-- Auteur  : Nicolas Scapino
-- Version : 1.0
--
-- 6 TABLES dans l'ordre de dépendance (les FK vont du bas vers le haut) :
--
--   1. athlete          — profil unique de l'athlète (1 seule ligne)
--   2. activities       — toutes les sorties importées depuis Strava
--   3. planned_sessions — séances planifiées par le coach
--   4. competitions     — objectifs course A / B / C sur la saison
--   5. coach_comments   — commentaires coach ou athlète sur une activité
--   6. llm_analyses     — cache des réponses OpenRouter (évite les doublons)
--
-- Ordre de construction recommandé : dans l'ordre ci-dessus,
-- car planned_sessions et coach_comments référencent activities.
-- =============================================================================


-- =============================================================================
-- TABLE 1 — athlete
-- -----------------------------------------------------------------------------
-- Profil unique de l'athlète. Une seule ligne, mise à jour à chaque ouverture
-- de l'app via UPSERT (INSERT ... ON CONFLICT DO UPDATE).
--
-- Pourquoi une seule ligne ?
--   → L'app est mono-athlète. On stocke les constantes d'entraînement ici
--     (FTP, poids, zones) pour les réutiliser dans tous les calculs métier
--     sans les passer en paramètre à chaque fois.
-- =============================================================================

CREATE TABLE IF NOT EXISTS athlete (
    id                  SERIAL PRIMARY KEY,

    -- Identité Strava (récupérée via l'API OAuth)
    strava_id           BIGINT UNIQUE NOT NULL,     -- ID unique Strava (ex: 139154618)
    firstname           VARCHAR(100),
    lastname            VARCHAR(100),
    city                VARCHAR(100),
    country             VARCHAR(100),
    profile_pic_url     TEXT,                       -- URL avatar Strava

    -- Constantes d'entraînement (mises à jour manuellement ou via profil)
    ftp_watts           INT DEFAULT 237,            -- Functional Threshold Power (watts)
    weight_kg           NUMERIC(5,2) DEFAULT 71.0,  -- Poids en kg (pour calcul w/kg)

    -- Zones de puissance (calculées automatiquement depuis FTP)
    -- Stockées en JSON pour éviter 7 colonnes supplémentaires
    -- Format : {"z1": [0,115], "z2": [115,157], ..., "z7": [322,999]}
    power_zones         JSONB,

    -- Statistiques YTD (Year To Date) — mises à jour à chaque refresh
    ytd_distance_km     NUMERIC(8,2),
    ytd_elevation_m     INT,
    ytd_time_hours      NUMERIC(6,2),

    -- Métadonnées
    last_synced_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index sur strava_id pour le UPSERT rapide
CREATE UNIQUE INDEX IF NOT EXISTS idx_athlete_strava_id ON athlete(strava_id);


-- =============================================================================
-- TABLE 2 — activities
-- -----------------------------------------------------------------------------
-- Toutes les sorties importées depuis Strava. Ingestion incrémentale :
-- on importe uniquement les activités postérieures à la dernière date connue
-- (requête avec after= sur l'API Strava).
--
-- Colonnes calculées à l'ingestion (pas stockées par Strava, calculées en Python) :
--   - distance_km      : metres / 1000
--   - moving_time_min  : seconds / 60
--   - avg_speed_kmh    : m/s × 3.6
--   - IF (Intensity Factor) : NP / FTP
--   - TSS (Training Stress Score) : (duration_s × NP × IF) / (FTP × 3600) × 100
--
-- Anti-doublon : ON CONFLICT (strava_id) DO NOTHING
--   → Si on relance l'ingestion, les activités déjà présentes sont ignorées.
-- =============================================================================

CREATE TABLE IF NOT EXISTS activities (
    id                  SERIAL PRIMARY KEY,

    -- Clé Strava — garantit l'unicité, utilisée pour l'anti-doublon
    strava_id           BIGINT UNIQUE NOT NULL,

    -- Données brutes Strava
    name                VARCHAR(255),               -- Nom de la sortie (ex: "Sortie vélo matin")
    sport_type          VARCHAR(50),                -- "Ride", "Run", "VirtualRide", etc.
    start_date          TIMESTAMP WITH TIME ZONE,   -- Date/heure de début (UTC)
    start_date_local    TIMESTAMP WITH TIME ZONE,   -- Date/heure locale (affichage calendrier)

    -- Métriques brutes (unités Strava)
    distance_m          NUMERIC(10,2),              -- Distance en mètres
    moving_time_s       INT,                        -- Temps en mouvement (secondes)
    elapsed_time_s      INT,                        -- Temps total écoulé (secondes)
    elevation_gain_m    NUMERIC(8,2),               -- Dénivelé positif (mètres)
    avg_watts           NUMERIC(8,2),               -- Puissance moyenne (watts)
    weighted_avg_watts  NUMERIC(8,2),               -- Normalized Power / NP (watts)
    max_watts           INT,                        -- Puissance max (watts)
    avg_heartrate       NUMERIC(5,2),               -- FC moyenne (bpm)
    max_heartrate       INT,                        -- FC max (bpm)
    avg_cadence         NUMERIC(5,2),               -- Cadence moyenne (rpm)
    kilojoules          NUMERIC(8,2),               -- Énergie dépensée (kJ)
    suffer_score        INT,                        -- Score Strava (optionnel)

    -- Colonnes calculées à l'ingestion (Python les calcule avant INSERT)
    distance_km         NUMERIC(8,3),               -- distance_m / 1000
    moving_time_min     NUMERIC(8,2),               -- moving_time_s / 60
    avg_speed_kmh       NUMERIC(6,2),               -- vitesse moy en km/h
    intensity_factor    NUMERIC(5,3),               -- IF = NP / FTP  (ex: 0.847)
    tss                 NUMERIC(8,2),               -- Training Stress Score

    -- Lien vers les données brutes Strava (streams) — stocké en JSON
    -- Contient : time[], watts[], heartrate[], cadence[] pour les graphiques
    streams_json        JSONB,

    -- Métadonnées
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index sur la date locale pour les requêtes calendrier (WHERE start_date_local::date = ...)
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(start_date_local);

-- Index sur sport_type pour filtrer uniquement les sorties vélo
CREATE INDEX IF NOT EXISTS idx_activities_sport ON activities(sport_type);


-- =============================================================================
-- TABLE 3 — planned_sessions
-- -----------------------------------------------------------------------------
-- Séances planifiées par le coach sur le calendrier.
-- C'est la table centrale du planning : elle est lue à chaque affichage
-- du calendrier pour savoir ce qui était prévu chaque jour.
--
-- Cycle de vie d'une séance :
--   planned → completed (si activité Strava matchée)
--           → missed    (si date passée sans activité)
--           → cancelled (supprimée par le coach)
--
-- Le matching Python compare la description du coach avec l'activité Strava
-- réelle et produit un statut de validation (✅ / ❌ / ⏳).
-- =============================================================================

CREATE TABLE IF NOT EXISTS planned_sessions (
    id                  SERIAL PRIMARY KEY,

    -- Quand ? (date uniquement, pas d'heure — le coach planifie à la journée)
    session_date        DATE NOT NULL,

    -- Contenu de la séance (saisi par le coach)
    title               VARCHAR(255) NOT NULL,      -- ex: "Tempo 2×20min"
    description         TEXT,                       -- ex: "2 blocs 20min à 85-90% FTP, récup 5min"
    sport_type          VARCHAR(50) DEFAULT 'Ride', -- Type d'effort attendu

    -- Cibles métriques (optionnel — pour le matching automatique)
    target_duration_min INT,                        -- Durée cible (minutes)
    target_tss          NUMERIC(6,2),               -- TSS cible
    target_if_min       NUMERIC(4,3),               -- IF minimum attendu
    target_if_max       NUMERIC(4,3),               -- IF maximum attendu
    target_distance_km  NUMERIC(7,2),               -- Distance cible (km)

    -- Statut du cycle de vie
    status              VARCHAR(20) DEFAULT 'planned'
                        CHECK (status IN ('planned', 'completed', 'missed', 'cancelled')),

    -- Lien vers l'activité Strava qui correspond à cette séance
    -- NULL tant que le matching n'a pas trouvé d'activité
    activity_id         INT REFERENCES activities(id) ON DELETE SET NULL,

    -- Résultat du matching Python + LLM
    validated           BOOLEAN,                    -- TRUE = ✅ / FALSE = ❌ / NULL = ⏳
    validation_score    NUMERIC(5,2),               -- Score 0-100 du matching
    validation_detail   JSONB,                      -- Détail critère par critère

    -- Ressenti athlète (saisi depuis le panneau latéral)
    ressenti            INT CHECK (ressenti BETWEEN 1 AND 5),  -- 1=très facile, 5=épuisant
    fatigue             INT CHECK (fatigue BETWEEN 1 AND 5),   -- 1=frais, 5=épuisé
    athlete_comment     TEXT,                       -- Commentaire libre de l'athlète

    -- Qui a créé cette séance ? (coach ou athlète)
    created_by          VARCHAR(50) DEFAULT 'coach',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index sur la date pour les requêtes semaine/mois du calendrier
CREATE INDEX IF NOT EXISTS idx_sessions_date ON planned_sessions(session_date);

-- Index sur le statut pour filtrer les séances non réalisées
CREATE INDEX IF NOT EXISTS idx_sessions_status ON planned_sessions(status);


-- =============================================================================
-- TABLE 4 — competitions
-- -----------------------------------------------------------------------------
-- Objectifs course sur la saison. Logique différente des séances :
--   - Pas de validation automatique (pas de critères métriques à remplir)
--   - Résultat saisi manuellement APRÈS la course
--   - Affiché différemment sur le calendrier (bandeau 🏆, couleur par niveau)
--   - LLM génère un bilan post-course quand le résultat est saisi
--
-- Niveaux d'objectif :
--   A = objectif principal de la saison (ex: championnat national)
--   B = objectif intermédiaire (ex: course régionale)
--   C = course d'entraînement (ex: critérium local)
-- =============================================================================

CREATE TABLE IF NOT EXISTS competitions (
    id                  SERIAL PRIMARY KEY,

    -- Quand et quoi ?
    competition_date    DATE NOT NULL,
    name                VARCHAR(255) NOT NULL,      -- ex: "Circuit de Assen"
    location            VARCHAR(255),               -- ex: "Assen, Pays-Bas"
    sport_type          VARCHAR(50) DEFAULT 'Ride',
    distance_km         NUMERIC(7,2),               -- Distance de la course

    -- Niveau d'objectif (A/B/C) — conditionne l'affichage sur le calendrier
    -- A → rouge/orange vif   B → bleu moyen   C → gris/vert discret
    objective_level     CHAR(1) NOT NULL DEFAULT 'B'
                        CHECK (objective_level IN ('A', 'B', 'C')),

    -- Notes de préparation (avant la course)
    preparation_notes   TEXT,                       -- Stratégie, objectif de temps, etc.

    -- Résultat — saisi manuellement après la course
    result_time         INTERVAL,                   -- Temps réalisé (ex: '02:34:15')
    result_rank         INT,                        -- Classement (ex: 12)
    result_participants INT,                        -- Nombre de participants
    result_distance_km  NUMERIC(7,2),               -- Distance réelle (si différente)
    ressenti            INT CHECK (ressenti BETWEEN 1 AND 5),  -- Ressenti global 1-5
    result_notes        TEXT,                       -- Commentaire post-course

    -- Lien vers l'activité Strava correspondante (matchée automatiquement par date)
    activity_id         INT REFERENCES activities(id) ON DELETE SET NULL,

    -- Bilan LLM post-course (généré automatiquement quand le résultat est saisi)
    llm_analysis_id     INT,                        -- FK vers llm_analyses (ajoutée après)

    -- Métadonnées
    created_by          VARCHAR(50) DEFAULT 'coach',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index sur la date pour affichage calendrier
CREATE INDEX IF NOT EXISTS idx_competitions_date ON competitions(competition_date);

-- Index sur le niveau pour filtrer les compétitions A uniquement
CREATE INDEX IF NOT EXISTS idx_competitions_level ON competitions(objective_level);


-- =============================================================================
-- TABLE 5 — coach_comments
-- -----------------------------------------------------------------------------
-- Commentaires libres du coach ou de l'athlète sur une activité Strava.
-- Séparés de planned_sessions pour pouvoir commenter des activités libres
-- (sorties non planifiées qui apparaissent quand même dans Strava).
--
-- Un commentaire est toujours lié à une activité (activity_id obligatoire).
-- Il peut aussi être lié à une séance planifiée (session_id optionnel).
--
-- author_role : 'coach' ou 'athlete' — permet d'afficher différemment
--   (bulle gauche / droite dans le panneau latéral, à la manière d'un chat)
-- =============================================================================

CREATE TABLE IF NOT EXISTS coach_comments (
    id                  SERIAL PRIMARY KEY,

    -- Lien obligatoire vers l'activité commentée
    activity_id         INT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,

    -- Lien optionnel vers la séance planifiée associée
    session_id          INT REFERENCES planned_sessions(id) ON DELETE SET NULL,

    -- Contenu
    author_role         VARCHAR(20) NOT NULL DEFAULT 'coach'
                        CHECK (author_role IN ('coach', 'athlete')),
    comment             TEXT NOT NULL,

    -- Métadonnées
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index sur activity_id — requête la plus fréquente : "commentaires de cette activité"
CREATE INDEX IF NOT EXISTS idx_comments_activity ON coach_comments(activity_id);


-- =============================================================================
-- TABLE 6 — llm_analyses
-- -----------------------------------------------------------------------------
-- Cache des réponses OpenRouter. Évite de rappeler le LLM pour la même analyse.
--
-- Logique de cache :
--   1. Avant d'appeler OpenRouter, on cherche une entrée avec le même
--      (analysis_type, entity_type, entity_id) datant de moins de X heures.
--   2. Si trouvée → on retourne le cached_response directement.
--   3. Si non trouvée → on appelle OpenRouter, on stocke ici, on retourne.
--
-- Types d'analyse possibles (analysis_type) :
--   'activity'    → synthèse d'une activité Strava
--   'validation'  → résultat du matching séance prévue vs réalisée
--   'competition' → bilan post-course
--   'week'        → synthèse de semaine
--   'block'       → synthèse d'un bloc d'entraînement
--   'ask'         → question libre de l'athlète
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_analyses (
    id                  SERIAL PRIMARY KEY,

    -- De quel type d'analyse s'agit-il ?
    analysis_type       VARCHAR(50) NOT NULL,       -- Voir liste ci-dessus

    -- Sur quelle entité porte cette analyse ?
    entity_type         VARCHAR(50),                -- 'activity', 'session', 'competition', 'week'
    entity_id           INT,                        -- ID de l'entité concernée

    -- Payload envoyé au LLM (le JSON canonique compressé)
    -- Stocké pour debug et audit : on peut retracer exactement ce qui a été envoyé
    input_payload       JSONB NOT NULL,

    -- Prompt complet envoyé à OpenRouter
    prompt_text         TEXT,

    -- Réponse brute du LLM
    cached_response     TEXT NOT NULL,

    -- Quel modèle a généré cette réponse ?
    model_used          VARCHAR(100),               -- ex: "mistralai/mixtral-8x7b-instruct"

    -- Métriques de l'appel (pour monitoring des coûts)
    tokens_input        INT,
    tokens_output       INT,
    latency_ms          INT,                        -- Temps de réponse OpenRouter (ms)

    -- Durée de validité du cache
    -- Passé ce délai, une nouvelle analyse sera demandée au LLM
    expires_at          TIMESTAMP WITH TIME ZONE,

    -- Métadonnées
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index composite pour la recherche de cache
-- Requête type : "y a-t-il déjà une analyse 'activity' pour l'activity_id 42 ?"
CREATE INDEX IF NOT EXISTS idx_llm_entity ON llm_analyses(analysis_type, entity_type, entity_id);

-- Index sur expires_at pour nettoyer les entrées expirées (job de maintenance)
CREATE INDEX IF NOT EXISTS idx_llm_expires ON llm_analyses(expires_at);


-- =============================================================================
-- FK DIFFÉRÉE — competitions.llm_analysis_id → llm_analyses.id
-- -----------------------------------------------------------------------------
-- Cette FK ne peut pas être déclarée dans CREATE TABLE competitions car
-- llm_analyses n'existait pas encore. On l'ajoute ici, en fin de script.
-- =============================================================================

ALTER TABLE competitions
    ADD CONSTRAINT fk_competitions_llm
    FOREIGN KEY (llm_analysis_id)
    REFERENCES llm_analyses(id)
    ON DELETE SET NULL;


-- =============================================================================
-- VUE UTILITAIRE — calendar_view
-- -----------------------------------------------------------------------------
-- Agrège pour chaque date ce qu'il faut afficher dans une case du calendrier.
-- Utilisée par la route GET /calendar/week?date=...
--
-- La vue retourne une ligne par date avec :
--   - La séance planifiée (si elle existe)
--   - L'activité Strava (si elle existe)
--   - La compétition (si elle existe)
--   - Le badge de validation (✅ / ❌ / ⏳)
--
-- Priorité d'affichage : compétition > séance planifiée > activité libre
-- =============================================================================

CREATE OR REPLACE VIEW calendar_view AS
SELECT
    -- Date pivot (source : séance prévue OU activité OU compétition)
    COALESCE(
        ps.session_date,
        a.start_date_local::DATE,
        c.competition_date
    )                                               AS calendar_date,

    -- Séance planifiée
    ps.id                                           AS session_id,
    ps.title                                        AS session_title,
    ps.description                                  AS session_description,
    ps.status                                       AS session_status,
    ps.validated                                    AS session_validated,
    ps.ressenti                                     AS session_ressenti,

    -- Activité Strava réalisée
    a.id                                            AS activity_id,
    a.name                                          AS activity_name,
    a.moving_time_min,
    a.weighted_avg_watts,
    a.avg_heartrate,
    a.tss,
    a.intensity_factor,

    -- Compétition
    c.id                                            AS competition_id,
    c.name                                          AS competition_name,
    c.objective_level,                              -- A / B / C → couleur bandeau
    c.result_rank,

    -- Badge synthétique pour l'affichage de la case
    CASE
        WHEN c.id IS NOT NULL               THEN '🏆'
        WHEN ps.validated = TRUE            THEN '✅'
        WHEN ps.validated = FALSE           THEN '❌'
        WHEN ps.id IS NOT NULL AND a.id IS NULL
             AND ps.session_date < CURRENT_DATE THEN '❌'
        WHEN ps.id IS NOT NULL AND a.id IS NULL THEN '⏳'
        WHEN a.id IS NOT NULL AND ps.id IS NULL THEN '🚴'  -- Activité libre (non planifiée)
        ELSE '⬜'
    END                                             AS badge

FROM planned_sessions ps
    FULL OUTER JOIN activities a
        ON a.start_date_local::DATE = ps.session_date
        AND ps.activity_id = a.id
    FULL OUTER JOIN competitions c
        ON c.competition_date = COALESCE(ps.session_date, a.start_date_local::DATE);


-- =============================================================================
-- FIN DU SCHEMA
-- Pour appliquer : psql -U <user> -d <database> -f schema.sql
-- Pour reset complet (dev uniquement) :
--   DROP VIEW IF EXISTS calendar_view;
--   DROP TABLE IF EXISTS llm_analyses, coach_comments, competitions,
--                        planned_sessions, activities, athlete CASCADE;
-- =============================================================================
