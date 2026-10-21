CREATE TABLE IF NOT EXISTS observation_rate_limits (
 client_hash TEXT NOT NULL, window_start BIGINT NOT NULL, attempts INTEGER NOT NULL,
 PRIMARY KEY(client_hash,window_start)
);
CREATE INDEX IF NOT EXISTS observation_rate_expiry_idx ON observation_rate_limits(window_start);
CREATE UNIQUE INDEX IF NOT EXISTS observation_submission_key_idx ON observations(submission_key);
