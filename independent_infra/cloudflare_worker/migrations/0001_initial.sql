PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS licenses (
    id TEXT PRIMARY KEY,
    key_digest TEXT NOT NULL UNIQUE,
    key_preview TEXT NOT NULL,
    discord_user_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    device_limit INTEGER NOT NULL CHECK(device_limit BETWEEN 1 AND 25),
    modules_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS license_devices (
    license_id TEXT NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
    hwid_digest TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    app_version TEXT NOT NULL,
    PRIMARY KEY (license_id, hwid_digest)
);

CREATE INDEX IF NOT EXISTS idx_licenses_expires_at
    ON licenses(expires_at);
CREATE INDEX IF NOT EXISTS idx_licenses_discord_user_id
    ON licenses(discord_user_id);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen_at
    ON license_devices(last_seen_at);
