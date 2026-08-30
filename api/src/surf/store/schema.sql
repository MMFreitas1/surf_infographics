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

-- Ground truth. Append-only, and written ONLY by the labeling UI (ADR-0006): no pipeline
-- stage, detector or migration may write here. A correction does not edit a row, it adds
-- one naming the row it replaces, so how judgement changed is part of the record.
--
-- The foreign key is deliberately NOT `ON DELETE CASCADE`. Deleting an activity that
-- carries labels fails, loudly, rather than quietly taking hours of human judgement with
-- it. Losing truth has to be harder than losing anything derived from it.
CREATE TABLE IF NOT EXISTS labels (
    label_id    TEXT    PRIMARY KEY,
    activity_id TEXT    NOT NULL REFERENCES activities (activity_id),
    t_start     REAL    NOT NULL,
    t_end       REAL    NOT NULL,
    is_wave     INTEGER NOT NULL,          -- 0 | 1: "this is not a ride" is also truth
    source      TEXT    NOT NULL,          -- human | human_assisted | ciq_bootstrap
    verified    INTEGER NOT NULL,          -- 0 | 1
    direction   TEXT    NOT NULL,          -- left | right | straight | unknown
    note        TEXT    NOT NULL DEFAULT '',
    created_at  REAL    NOT NULL,
    supersedes  TEXT    REFERENCES labels (label_id)
);

-- A completed sweep of a session. Needed because a count of labels cannot tell a session
-- nobody has opened from one somebody swept carefully and found no rides in -- and the
-- blind pass is the gate on the assisted one (ADR-0012), so it must be recorded, not
-- inferred. Re-sweeping appends another row rather than replacing the first.
CREATE TABLE IF NOT EXISTS label_passes (
    activity_id  TEXT    NOT NULL REFERENCES activities (activity_id),
    kind         TEXT    NOT NULL,         -- blind | assisted
    completed_at REAL    NOT NULL,
    label_count  INTEGER NOT NULL,
    PRIMARY KEY (activity_id, kind, completed_at)
);

CREATE INDEX IF NOT EXISTS idx_labels_activity ON labels (activity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_labels_supersedes ON labels (supersedes);
CREATE INDEX IF NOT EXISTS idx_label_passes_activity ON label_passes (activity_id);
