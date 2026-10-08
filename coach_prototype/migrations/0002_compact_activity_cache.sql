-- Coach-only migration. Run against coach_proto after backing it up.
-- Safe to apply repeatedly. Does not reference the legacy Stravbike database.
ALTER TABLE coach_users
    ADD COLUMN IF NOT EXISTS max_heartrate INTEGER;

ALTER TABLE coach_strava_connections
    ADD COLUMN IF NOT EXISTS last_activity_sync_at TIMESTAMPTZ;

ALTER TABLE coach_activities
    ADD COLUMN IF NOT EXISTS moving_time_s INTEGER,
    ADD COLUMN IF NOT EXISTS elapsed_time_s INTEGER,
    ADD COLUMN IF NOT EXISTS elevation_gain_m NUMERIC(9,2),
    ADD COLUMN IF NOT EXISTS avg_heartrate INTEGER,
    ADD COLUMN IF NOT EXISTS avg_cadence INTEGER,
    ADD COLUMN IF NOT EXISTS device_watts BOOLEAN,
    ADD COLUMN IF NOT EXISTS streams_json JSON,
    ADD COLUMN IF NOT EXISTS compact_json JSON,
    ADD COLUMN IF NOT EXISTS best_json JSON;

-- Strava activity IDs are 64-bit values; keep external IDs lossless.
ALTER TABLE coach_activities
    ALTER COLUMN source_id TYPE BIGINT USING source_id::BIGINT;

CREATE INDEX IF NOT EXISTS ix_coach_activities_user_occurred
    ON coach_activities (user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS coach_level_cache (
    user_id INTEGER PRIMARY KEY REFERENCES coach_users(id) ON DELETE CASCADE,
    snapshot_json JSON NOT NULL,
    source_signature VARCHAR(64) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);
