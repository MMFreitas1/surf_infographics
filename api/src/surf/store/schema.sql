-- Local-first storage (ADR-0004). One file, no server, no migrations tool.
--
-- Metadata lives here; samples do not. A session's ~4k samples are a pipeline stage
-- output (L0), so they go to Parquet through the same content-addressed StageCache every
-- later stage uses, and the activities row keeps the key. See docs/architecture.md §2.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id      TEXT    PRIMARY KEY,
    source_sha256    TEXT    NOT NULL UNIQUE,  -- one upload of one file is one activity
    sport            TEXT    NOT NULL,
    start_time       REAL    NOT NULL,
    fidelity         TEXT    NOT NULL,         -- fit | tcx | gpx (ADR-0002)
    device           TEXT    NOT NULL DEFAULT '',
    source_file      TEXT    NOT NULL DEFAULT '',
    sample_count     INTEGER NOT NULL,
    positioned_count INTEGER NOT NULL,         -- stored, not derived: coverage is a headline number
    duration_s       REAL    NOT NULL,
    blind_seconds    REAL    NOT NULL,
    samples_key      TEXT    NOT NULL,         -- StageCache key for the L0 Parquet payload
    ingested_at      REAL    NOT NULL
);

-- Blind windows are first-class objects, not an absence (ADR-0003), so they are rows we
-- can query -- not a blob buried inside the samples file.
CREATE TABLE IF NOT EXISTS blind_windows (
    activity_id TEXT    NOT NULL REFERENCES activities (activity_id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    t_start     REAL    NOT NULL,
    t_end       REAL    NOT NULL,
    cause       TEXT    NOT NULL,  -- no_fix | missing_record | unknown
    PRIMARY KEY (activity_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_activities_start_time ON activities (start_time DESC);
CREATE INDEX IF NOT EXISTS idx_blind_windows_activity ON blind_windows (activity_id);
