-- Stock Analytics Platform schema. Safe to run more than once.

CREATE TABLE IF NOT EXISTS companies (
    symbol   TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    sector   TEXT,
    industry TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    symbol         TEXT NOT NULL REFERENCES companies(symbol),
    date           DATE NOT NULL,
    open           NUMERIC,
    high           NUMERIC,
    low            NUMERIC,
    close          NUMERIC NOT NULL,
    adjusted_close NUMERIC NOT NULL,
    volume         BIGINT,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS prices_symbol_date ON prices (symbol, date);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id             BIGSERIAL PRIMARY KEY,
    run_id         TEXT NOT NULL,
    symbol         TEXT,
    status         TEXT NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_fetched   INT NOT NULL DEFAULT 0,
    api_calls_used INT NOT NULL DEFAULT 0,
    message        TEXT
);
CREATE INDEX IF NOT EXISTS ingestion_log_started ON ingestion_log (started_at);

CREATE TABLE IF NOT EXISTS holdings (
    id       BIGSERIAL PRIMARY KEY,
    user_id  TEXT NOT NULL,
    symbol   TEXT NOT NULL REFERENCES companies(symbol),
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    avg_cost NUMERIC NOT NULL CHECK (avg_cost >= 0)
);
CREATE INDEX IF NOT EXISTS holdings_user ON holdings (user_id);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id TEXT NOT NULL,
    symbol  TEXT NOT NULL REFERENCES companies(symbol),
    PRIMARY KEY (user_id, symbol)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    symbol     TEXT NOT NULL REFERENCES companies(symbol),
    direction  TEXT NOT NULL CHECK (direction IN ('above', 'below')),
    threshold  NUMERIC NOT NULL,
    active     BOOLEAN NOT NULL DEFAULT true,
    last_state TEXT
);
CREATE INDEX IF NOT EXISTS alert_rules_symbol ON alert_rules (symbol) WHERE active;

CREATE TABLE IF NOT EXISTS alerts (
    id           BIGSERIAL PRIMARY KEY,
    rule_id      BIGINT REFERENCES alert_rules(id) ON DELETE SET NULL,
    symbol       TEXT NOT NULL,
    price        NUMERIC NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alerts_time ON alerts (triggered_at DESC);
