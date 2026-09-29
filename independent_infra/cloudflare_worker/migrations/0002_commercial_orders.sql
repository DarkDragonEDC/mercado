CREATE TABLE IF NOT EXISTS commercial_orders (
    id TEXT PRIMARY KEY,
    discord_user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    plan_id TEXT NOT NULL CHECK(plan_id IN ('compra', 'venda', 'completo')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    status TEXT NOT NULL CHECK(status IN ('creating', 'pending', 'processing', 'approved', 'rejected', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    preference_id TEXT,
    payment_id TEXT UNIQUE,
    license_id TEXT REFERENCES licenses(id),
    license_secret TEXT,
    access_expires_at TEXT,
    delivered_at TEXT,
    delivery_error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_commercial_orders_user
    ON commercial_orders(discord_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_orders_status
    ON commercial_orders(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_commercial_orders_expiration
    ON commercial_orders(access_expires_at);
