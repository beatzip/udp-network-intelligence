"""Stub: Initial database migration."""

from __future__ import annotations

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS probe_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_host TEXT NOT NULL,
    target_port INTEGER NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent INTEGER NOT NULL DEFAULT 0,
    received INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    min_rtt REAL NOT NULL DEFAULT 0.0,
    max_rtt REAL NOT NULL DEFAULT 0.0,
    avg_rtt REAL NOT NULL DEFAULT 0.0,
    jitter REAL NOT NULL DEFAULT 0.0,
    quality_grade TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_probe_target
    ON probe_results(target_host, target_port);

CREATE INDEX IF NOT EXISTS idx_probe_timestamp
    ON probe_results(timestamp);
"""
