
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_records (
    record_id           VARCHAR PRIMARY KEY,
    provider            VARCHAR NOT NULL,
    account_id          VARCHAR NOT NULL,
    api_key_id          VARCHAR,
    user_id             VARCHAR,
    project_id          VARCHAR,
    workspace_id        VARCHAR,
    model               VARCHAR,
    operation           VARCHAR,
    region              VARCHAR,
    service_tier        VARCHAR,
    charge_category     VARCHAR NOT NULL,
    input_tokens        BIGINT  NOT NULL DEFAULT 0,
    output_tokens       BIGINT  NOT NULL DEFAULT 0,
    cache_read_tokens   BIGINT  NOT NULL DEFAULT 0,
    cache_write_tokens  BIGINT  NOT NULL DEFAULT 0,
    reasoning_tokens    BIGINT  NOT NULL DEFAULT 0,
    requests            BIGINT  NOT NULL DEFAULT 0,
    seats               INTEGER NOT NULL DEFAULT 0,
    input_cost          DECIMAL(38,12) NOT NULL DEFAULT 0,
    output_cost         DECIMAL(38,12) NOT NULL DEFAULT 0,
    cache_read_cost     DECIMAL(38,12) NOT NULL DEFAULT 0,
    cache_write_cost    DECIMAL(38,12) NOT NULL DEFAULT 0,
    seat_cost           DECIMAL(38,12) NOT NULL DEFAULT 0,
    batch_discount      DECIMAL(38,12) NOT NULL DEFAULT 0,
    tier_adjustment     DECIMAL(38,12) NOT NULL DEFAULT 0,
    other_cost          DECIMAL(38,12) NOT NULL DEFAULT 0,
    billed_cost         DECIMAL(38,12) NOT NULL,
    list_cost           DECIMAL(38,12),
    currency            VARCHAR NOT NULL,
    fx_rate_date        DATE,
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL,
    cost_centre         VARCHAR,
    parent_entity       VARCHAR,
    allocation_method   VARCHAR NOT NULL,
    source              VARCHAR NOT NULL,
    completeness        VARCHAR NOT NULL,
    extensions          JSON
);

CREATE INDEX IF NOT EXISTS idx_usage_period  ON usage_records (period_start);
CREATE INDEX IF NOT EXISTS idx_usage_key     ON usage_records (provider, api_key_id);
CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_records (project_id);

CREATE TABLE IF NOT EXISTS watermarks (
    connector    VARCHAR PRIMARY KEY,
    -- Not `position`: that is a SQL function name.
    collected_to TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id       VARCHAR PRIMARY KEY,
    rule           VARCHAR NOT NULL,
    severity       VARCHAR NOT NULL,
    provider       VARCHAR NOT NULL,
    credential     VARCHAR NOT NULL,
    -- Not `at`: reserved word in DuckDB.
    occurred_at    TIMESTAMPTZ NOT NULL,
    observed       DECIMAL(38,12) NOT NULL,
    baseline       DECIMAL(38,12) NOT NULL,
    multiple       DECIMAL(38,12),
    spend_so_far   DECIMAL(38,12) NOT NULL,
    projected_24h  DECIMAL(38,12) NOT NULL,
    currency       VARCHAR NOT NULL,
    confidence     VARCHAR NOT NULL,
    evidence       JSON,
    created_at     TIMESTAMPTZ NOT NULL,
    notified_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_at ON alerts (occurred_at);

CREATE TABLE IF NOT EXISTS budget_thresholds (
    budget_id     VARCHAR NOT NULL,
    period_start  TIMESTAMPTZ NOT NULL,
    threshold     DECIMAL(10,4) NOT NULL,
    crossed_at    TIMESTAMPTZ NOT NULL,
    notified_at   TIMESTAMPTZ,
    PRIMARY KEY (budget_id, period_start, threshold)
);
