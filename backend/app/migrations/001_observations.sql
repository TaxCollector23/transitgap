CREATE TABLE IF NOT EXISTS observations (
 id TEXT PRIMARY KEY, latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
 category TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 evidence_status TEXT NOT NULL DEFAULT 'COMMUNITY_REPORTED', review_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
 related_feature_id TEXT, optional_source_reference TEXT, source TEXT NOT NULL DEFAULT 'community',
 edge_reference TEXT, routing_effect TEXT NOT NULL DEFAULT 'none', effective_until TEXT, affected_profiles TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS observations_created_at_idx ON observations(created_at DESC);
CREATE INDEX IF NOT EXISTS observations_location_idx ON observations(latitude, longitude);
CREATE TABLE IF NOT EXISTS observation_reviews (
 id TEXT PRIMARY KEY, observation_id TEXT NOT NULL REFERENCES observations(id),
 previous_status TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL, edge_reference TEXT, routing_effect TEXT NOT NULL, effective_until TEXT, affected_profiles TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS observation_reviews_report_idx ON observation_reviews(observation_id, created_at);
CREATE TABLE IF NOT EXISTS observation_schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
