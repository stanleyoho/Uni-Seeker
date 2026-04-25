-- Create the sync_states table for tracking data synchronisation progress.

CREATE TABLE IF NOT EXISTS sync_states (
    id              SERIAL PRIMARY KEY,
    dataset         VARCHAR(50)   NOT NULL,
    stock_id        INTEGER       REFERENCES stocks(id) ON DELETE CASCADE,
    last_synced_date DATE,
    last_run_at     TIMESTAMPTZ,
    status          VARCHAR(20)   NOT NULL DEFAULT 'idle',
    error_message   VARCHAR(500),
    records_synced  INTEGER       NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT uq_sync_state UNIQUE (dataset, stock_id)
);

-- Index for fast lookups by dataset
CREATE INDEX IF NOT EXISTS ix_sync_states_dataset ON sync_states (dataset);
