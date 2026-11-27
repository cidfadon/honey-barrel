-- Initial schema for the Trading212 × OpenClaw stack
CREATE TABLE IF NOT EXISTS t212_calls (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    endpoint     TEXT NOT NULL,
    method       TEXT NOT NULL,
    payload      JSONB,
    response     JSONB,
    http_status  INT,
    latency_ms   INT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id        BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    cash      JSONB NOT NULL,
    positions JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    t212_order_id TEXT UNIQUE,
    ticker        TEXT NOT NULL,
    side          TEXT CHECK (side IN ('BUY','SELL')) NOT NULL,
    qty           NUMERIC(18,6) NOT NULL,
    order_type    TEXT NOT NULL,
    limit_price   NUMERIC(18,6),
    status        TEXT NOT NULL,
    raw           JSONB
);

CREATE TABLE IF NOT EXISTS llm_analyses (
    id                 BIGSERIAL PRIMARY KEY,
    ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshot_id        BIGINT REFERENCES portfolio_snapshots(id),
    model              TEXT NOT NULL,
    prompt             TEXT NOT NULL,
    completion         TEXT NOT NULL,
    decision           JSONB,
    triggered_order_id BIGINT REFERENCES orders(id)
);

CREATE INDEX IF NOT EXISTS idx_t212_calls_ts        ON t212_calls(ts DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_ts         ON portfolio_snapshots(ts DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(status);
CREATE INDEX IF NOT EXISTS idx_llm_analyses_ts      ON llm_analyses(ts DESC);
