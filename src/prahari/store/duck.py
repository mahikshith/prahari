"""DuckDB store - the collector's memory.

Without persistence there is no incremental collection, no resumable backfill, no
period-over-period comparison, and no alert deduplication. Every one of those is
required before a design partner can leave this running.

Three guarantees the rest of the system relies on:

**Upserts are idempotent.** Re-fetching a window must not double-count. Every record
gets a deterministic `record_id` hashed from its natural key, and a re-fetch replaces
rather than appends. This also handles the settling case correctly: a `PARTIAL` hour
fetched at 09:05 is overwritten by the `FINAL` version fetched at 10:00, rather than
both being counted.

**Watermarks are only advanced past settled data.** A window that a provider has not
finished filling must be re-fetched next cycle, so the watermark tracks the last
*complete* position, not the last position we asked about.

**Alerts are deduplicated by identity, not by content.** The same rule firing on the
same credential in the same hour is one alert however many times we evaluate it.

Concurrency: DuckDB permits one writer process. That suits a single collector daemon
and is the intended deployment. Multi-writer means Postgres, and that is a control-
plane concern, not a collector one.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from prahari.core.models import (
    AllocationMethod,
    ChargeCategory,
    Completeness,
    CostBasis,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)
from prahari.detect.rules import Alert, Rule, Severity
from prahari.notify.router import Message

SCHEMA_VERSION = 2

_NATURAL_KEY = (
    "provider",
    "account_id",
    "api_key_id",
    "user_id",
    "project_id",
    "workspace_id",
    "model",
    "operation",
    "region",
    "service_tier",
    "source",
    "currency",
    "charge_category",
)

DDL = """
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
    billed_cost         DECIMAL(38,12),
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
    cost_basis          VARCHAR NOT NULL DEFAULT 'provider_reported',
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
    observed       DECIMAL(38,12),
    baseline       DECIMAL(38,12),
    multiple       DECIMAL(38,12),
    spend_so_far   DECIMAL(38,12),
    projected_24h  DECIMAL(38,12),
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
    notification_id VARCHAR,
    PRIMARY KEY (budget_id, period_start, threshold)
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    event_id       VARCHAR NOT NULL,
    kind           VARCHAR NOT NULL,
    channel        VARCHAR NOT NULL,
    title          VARCHAR NOT NULL,
    body           VARCHAR NOT NULL,
    severity       VARCHAR NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL,
    delivered_at   TIMESTAMPTZ,
    next_attempt   TIMESTAMPTZ NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, channel)
);
"""

_COLUMNS = [
    line.strip().split()[0]
    for line in DDL.split("CREATE TABLE IF NOT EXISTS usage_records (")[1]
    .split(");")[0]
    .strip()
    .splitlines()
    if line.strip() and not line.strip().startswith(("PRIMARY", "--"))
]


def record_id(record: UsageRecord) -> str:
    """Deterministic identity for a record.

    Hashed from the natural key plus the period, so the same hour of the same
    credential on the same model always lands on the same row no matter how many
    times it is fetched. Stable across processes and runs - a Python `hash()` would
    not be.
    """
    parts = [str(getattr(record, field) or "") for field in _NATURAL_KEY]
    parts.extend(
        str(record.extensions.get(field) or "")
        for field in ("invoice_month", "cost_type", "service", "project_name")
    )
    parts.append(record.period_start.astimezone(UTC).isoformat())
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def alert_id(alert: Alert) -> str:
    """One alert per (rule, credential, hour). The same rule firing on the same
    credential in the same hour is one event however many evaluation cycles see it."""
    provider, credential = alert.detection_key
    raw = f"{alert.rule}\x1f{provider}\x1f{credential}\x1f{alert.at.astimezone(UTC).isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class Store:
    """Persistent store for records, watermarks and alert state."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(self.path)
        try:
            self._migrate()
        except Exception:
            self._con.close()
            raise

    def _migrate(self) -> None:
        self._con.execute(DDL)
        current = self._con.execute("SELECT max(version) FROM schema_meta").fetchone()[0]
        if current is not None and current > SCHEMA_VERSION:
            raise ValueError(f"store schema {current} is newer than supported {SCHEMA_VERSION}")
        if current is None:
            self._con.execute(
                "INSERT INTO schema_meta VALUES (?, ?)", [SCHEMA_VERSION, datetime.now(UTC)]
            )
        elif current < SCHEMA_VERSION:
            self._con.execute("BEGIN TRANSACTION")
            try:
                self._con.execute("DROP INDEX IF EXISTS idx_usage_period")
                self._con.execute("DROP INDEX IF EXISTS idx_usage_key")
                self._con.execute("DROP INDEX IF EXISTS idx_usage_project")
                self._con.execute("DROP INDEX IF EXISTS idx_alerts_at")
                self._con.execute(
                    "ALTER TABLE usage_records ALTER COLUMN billed_cost DROP NOT NULL"
                )
                self._con.execute(
                    "ALTER TABLE usage_records ADD COLUMN cost_basis "
                    "VARCHAR DEFAULT 'provider_reported'"
                )
                self._con.execute(
                    "UPDATE usage_records SET cost_basis = 'estimated' "
                    "WHERE completeness = 'estimated' OR source IN "
                    "('openai:/v1/organization/usage/completions', "
                    "'anthropic:/v1/organizations/usage_report/messages')"
                )
                self._con.execute(
                    "ALTER TABLE budget_thresholds ADD COLUMN notification_id VARCHAR"
                )
                for field in ("observed", "baseline", "spend_so_far", "projected_24h"):
                    self._con.execute(f"ALTER TABLE alerts ALTER COLUMN {field} DROP NOT NULL")
                records = self.records()
                self._con.execute("DELETE FROM usage_records")
                if records:
                    self._con.register(
                        "_migration",
                        pd.DataFrame(
                            [self._to_row(record) for record in records], columns=_COLUMNS
                        ),
                    )
                    try:
                        self._con.execute(
                            "INSERT INTO usage_records BY NAME SELECT * FROM _migration"
                        )
                    finally:
                        self._con.unregister("_migration")
                self._con.execute(
                    "INSERT INTO schema_meta VALUES (?, ?)", [SCHEMA_VERSION, datetime.now(UTC)]
                )
                self._con.execute("COMMIT")
            except Exception:
                with contextlib.suppress(duckdb.Error):
                    self._con.execute("ROLLBACK")
                raise
            self._con.execute(DDL)

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- records --------------------------------------------------------------

    def upsert_records(self, records: Iterable[UsageRecord]) -> int:
        """Insert or replace. Returns the number written.

        Replacement, not append: a PARTIAL hour fetched while it was still filling is
        overwritten by the FINAL version on the next pass, rather than both being
        counted.

        Deliberately set-based. DuckDB is an OLAP engine, and row-by-row
        `INSERT OR REPLACE` against a primary key measured **26 ms per row** - 200
        seconds for a single 7,440-record batch, which would have made incremental
        collection impossible. Registering the batch and doing delete-then-insert as
        two set operations is 0.05 ms/row, a ~540x difference.
        """
        rows = [self._to_row(r) for r in records]
        if not rows:
            return 0

        frame = pd.DataFrame(rows, columns=_COLUMNS)
        self._con.register("_batch", frame)
        try:
            # One transaction: a crash between the delete and the insert would
            # otherwise lose the rows being replaced.
            self._con.execute("BEGIN TRANSACTION")
            self._con.execute(
                "DELETE FROM usage_records WHERE record_id IN (SELECT record_id FROM _batch)"
            )
            legacy_match = " AND ".join(
                f"old.{name} IS NOT DISTINCT FROM fresh.{name}"
                for name in _NATURAL_KEY
                if name != "charge_category"
            )
            # Replace legacy GCP aggregates when their invoice/type groups are re-fetched.
            self._con.execute(
                "DELETE FROM usage_records AS old WHERE old.provider = 'gcp_vertex' "
                "AND json_extract_string(old.extensions,'$.invoice_month') IS NULL "
                "AND json_extract_string(old.extensions,'$.cost_type') IS NULL "
                "AND EXISTS (SELECT 1 FROM _batch AS fresh WHERE "
                f"{legacy_match} AND old.period_start = fresh.period_start "
                "AND json_extract_string(old.extensions,'$.service') IS NOT DISTINCT FROM "
                "json_extract_string(fresh.extensions,'$.service') "
                "AND json_extract_string(old.extensions,'$.project_name') IS NOT DISTINCT FROM "
                "json_extract_string(fresh.extensions,'$.project_name') "
                "AND (json_extract_string(fresh.extensions,'$.invoice_month') IS NOT NULL "
                "OR json_extract_string(fresh.extensions,'$.cost_type') IS NOT NULL))"
            )
            self._con.execute("INSERT INTO usage_records BY NAME SELECT * FROM _batch")
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        finally:
            self._con.unregister("_batch")

        return len(rows)

    def records(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        providers: Sequence[Provider] | None = None,
        settled_only: bool = False,
    ) -> list[UsageRecord]:
        """Read records back. `settled_only` excludes windows still filling, which is
        what reconciliation and any customer-facing total should use."""
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("period_start >= ?")
            params.append(start)
        if end is not None:
            clauses.append("period_start < ?")
            params.append(end)
        if providers:
            clauses.append(f"provider IN ({', '.join(['?'] * len(providers))})")
            params.extend(p.value for p in providers)
        if settled_only:
            clauses.append("completeness != ?")
            params.append(Completeness.PARTIAL.value)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = self._con.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM usage_records {where} ORDER BY period_start",
            params,
        )
        return [self._from_row(row) for row in cursor.fetchall()]

    def total_cost(self, start: datetime, end: datetime, currency: str = "INR") -> Decimal:
        """Sum the requested native currency; unknown costs make its total incomplete."""
        row = self._con.execute(
            """
            SELECT count(*) FILTER (WHERE billed_cost IS NULL), sum(billed_cost)
            FROM usage_records
            WHERE period_start >= ? AND period_start < ? AND currency = ?
            """,
            [start, end, currency.upper()],
        ).fetchone()
        if row[0]:
            raise ValueError(f"cost unavailable for {row[0]} usage records; total is incomplete")
        return Decimal(str(row[1] or 0))

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM usage_records").fetchone()[0]

    # --- watermarks -----------------------------------------------------------

    def watermark(self, connector: str) -> datetime | None:
        row = self._con.execute(
            "SELECT collected_to FROM watermarks WHERE connector = ?", [connector]
        ).fetchone()
        return _as_utc(row[0]) if row else None

    def set_watermark(self, connector: str, position: datetime) -> None:
        """Advance the watermark. Never moves backwards.

        A backfill of older data must not rewind the live collection position, or the
        daemon would re-fetch everything since and waste an entire cycle.
        """
        existing = self.watermark(connector)
        if existing is not None and position <= existing:
            return
        self._con.execute(
            "INSERT OR REPLACE INTO watermarks VALUES (?, ?, ?)",
            [connector, position, datetime.now(UTC)],
        )

    # --- alerts ---------------------------------------------------------------

    def record_alert(self, alert: Alert) -> bool:
        """Persist an alert. Returns True if it is new, False if already seen.

        The return value is the deduplication contract: callers notify only on True.
        An alerting system that repeats itself gets filtered into a folder nobody
        reads, which is operationally the same as having no alerts.
        """
        aid = alert_id(alert)
        seen = self._con.execute("SELECT 1 FROM alerts WHERE alert_id = ?", [aid]).fetchone()
        if seen:
            return False

        provider, credential = alert.detection_key
        self._con.execute(
            "INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                aid,
                str(alert.rule),
                str(alert.severity),
                provider,
                credential,
                alert.at,
                alert.observed,
                alert.baseline,
                alert.multiple,
                alert.spend_so_far,
                alert.projected_24h,
                alert.currency,
                alert.confidence,
                json.dumps(alert.evidence, default=str),
                datetime.now(UTC),
                None,
            ],
        )
        return True

    def mark_notified(self, alert: Alert) -> None:
        self._con.execute(
            "UPDATE alerts SET notified_at = ? WHERE alert_id = ?",
            [datetime.now(UTC), alert_id(alert)],
        )

    def pending_alerts(
        self, limit: int = 100, *, unqueued_only: bool = False
    ) -> list[dict[str, Any]]:
        """Alerts recorded but not yet delivered - the retry queue after an outage in
        Slack or SMTP."""
        unqueued = (
            "AND NOT EXISTS (SELECT 1 FROM notification_outbox WHERE event_id = alerts.alert_id)"
            if unqueued_only
            else ""
        )
        cursor = self._con.execute(
            f"""
            SELECT alert_id, rule, severity, provider, credential, occurred_at,
                   observed, baseline, multiple, spend_so_far, projected_24h, currency,
                   confidence, evidence
            FROM alerts WHERE notified_at IS NULL {unqueued}
            ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                     occurred_at ASC LIMIT ?
            """,
            [limit],
        )
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    # --- budget threshold state ----------------------------------------------

    def crossed_thresholds(self, budget_id: str, period_start: datetime) -> list[Decimal]:
        rows = self._con.execute(
            "SELECT threshold FROM budget_thresholds WHERE budget_id = ? AND period_start = ?",
            [budget_id, period_start],
        ).fetchall()
        return [Decimal(str(r[0])) for r in rows]

    def mark_threshold_crossed(
        self, budget_id: str, period_start: datetime, threshold: Decimal
    ) -> bool:
        """Returns True if newly crossed. Feeds `evaluate(already_crossed=...)` so a
        budget past 80% alerts once, not on every cycle forever."""
        already = self._con.execute(
            """
            SELECT 1 FROM budget_thresholds
            WHERE budget_id = ? AND period_start = ? AND threshold = ?
            """,
            [budget_id, period_start, threshold],
        ).fetchone()
        if already:
            return False
        self._con.execute(
            "INSERT INTO budget_thresholds "
            "(budget_id,period_start,threshold,crossed_at,notified_at) VALUES (?,?,?,?,?)",
            [budget_id, period_start, threshold, datetime.now(UTC), None],
        )
        return True

    def unqueued_thresholds(self, budget_id: str, period_start: datetime) -> list[Decimal]:
        rows = self._con.execute(
            "SELECT threshold FROM budget_thresholds "
            "WHERE budget_id = ? AND period_start = ? AND notification_id IS NULL",
            [budget_id, period_start],
        ).fetchall()
        return [row[0] for row in rows]

    def queue_notification(
        self, event_id: str, kind: str, message: Message, channels: Sequence[str]
    ) -> None:
        if not channels:
            return
        now = datetime.now(UTC)
        self._con.execute(
            "INSERT OR IGNORE INTO notification_outbox "
            "(event_id,kind,channel,title,body,severity,created_at,next_attempt) "
            "SELECT ?,?,channel,?,?,?,?,? FROM unnest(?) AS targets(channel) "
            "WHERE NOT EXISTS (SELECT 1 FROM notification_outbox WHERE event_id = ?)",
            [
                event_id,
                kind,
                message.title,
                message.body,
                str(message.severity),
                now,
                now,
                list(channels),
                event_id,
            ],
        )

    def queue_budget(
        self,
        budget_id: str,
        period_start: datetime,
        thresholds: Sequence[Decimal],
        message: Message,
        channels: Sequence[str],
    ) -> str:
        raw = f"{budget_id}\x1f{period_start.isoformat()}\x1f{sorted(thresholds)}"
        event_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
        self._con.execute("BEGIN TRANSACTION")
        try:
            self.queue_notification(event_id, "budget", message, channels)
            for threshold in thresholds:
                self._con.execute(
                    "UPDATE budget_thresholds SET notification_id = ? "
                    "WHERE budget_id = ? AND period_start = ? AND threshold = ?",
                    [event_id, budget_id, period_start, threshold],
                )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        return event_id

    def pending_notifications(
        self, now: datetime, limit: int = 100, *, channels: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if channels is not None and not channels:
            return []
        clause = ""
        params: list[Any] = [now]
        if channels is not None:
            clause = f"AND channel IN ({','.join('?' for _ in channels)}) "
            params.extend(channels)
        params.append(limit)
        cursor = self._con.execute(
            "SELECT * FROM notification_outbox WHERE delivered_at IS NULL "
            f"AND next_attempt <= ? {clause} ORDER BY "
            "CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
            "created_at, event_id, channel LIMIT ?",
            params,
        )
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def record_delivery(self, event_id: str, channel: str, success: bool, now: datetime) -> None:
        attempts = self._con.execute(
            "SELECT attempts FROM notification_outbox WHERE event_id = ? AND channel = ?",
            [event_id, channel],
        ).fetchone()[0]
        next_attempt = now + timedelta(seconds=min(300, 15 * 2 ** min(attempts, 5)))
        self._con.execute(
            "UPDATE notification_outbox SET delivered_at = ?, next_attempt = ?, "
            "attempts = attempts+1 "
            "WHERE event_id = ? AND channel = ?",
            [now if success else None, next_attempt, event_id, channel],
        )

    def next_notification_due(self, channels: Sequence[str]) -> datetime | None:
        if not channels:
            return None
        row = self._con.execute(
            "SELECT min(next_attempt) FROM notification_outbox WHERE delivered_at IS NULL "
            f"AND channel IN ({','.join('?' for _ in channels)})",
            list(channels),
        ).fetchone()
        return _as_utc(row[0]) if row[0] else None

    def notification_complete(self, event_id: str) -> bool:
        rows = self._con.execute(
            "SELECT channel,delivered_at FROM notification_outbox WHERE event_id = ?",
            [event_id],
        ).fetchall()
        required = [row for row in rows if row[0] != "console"] or rows
        return bool(required) and all(delivered_at is not None for _, delivered_at in required)

    def acknowledge_notification(self, event_id: str, kind: str) -> None:
        now = datetime.now(UTC)
        if kind == "alert":
            self._con.execute(
                "UPDATE alerts SET notified_at = ? WHERE alert_id = ?", [now, event_id]
            )
        else:
            self._con.execute(
                "UPDATE budget_thresholds SET notified_at = ? WHERE notification_id = ?",
                [now, event_id],
            )

    def unacknowledged_notifications(self) -> list[tuple[str, str]]:
        return self._con.execute(
            "SELECT DISTINCT event_id, kind FROM notification_outbox "
            "WHERE event_id IN (SELECT alert_id FROM alerts WHERE notified_at IS NULL) "
            "OR event_id IN (SELECT notification_id FROM budget_thresholds "
            "WHERE notified_at IS NULL)"
        ).fetchall()

    def last_activity_before(self, at: datetime) -> dict[tuple[str, str], datetime]:
        rows = self._con.execute(
            "SELECT provider, coalesce(nullif(api_key_id,''),nullif(user_id,''),"
            "nullif(project_id,''),account_id), max(period_start) "
            "FROM usage_records WHERE period_start < ? "
            "AND (billed_cost > 0 OR requests > 0 OR input_tokens > 0 OR output_tokens > 0 "
            "OR cache_read_tokens > 0 OR cache_write_tokens > 0 OR reasoning_tokens > 0) "
            "GROUP BY 1,2",
            [at],
        ).fetchall()
        return {
            (provider, credential): _as_utc(last_seen) for provider, credential, last_seen in rows
        }

    # --- row mapping ----------------------------------------------------------

    def _to_row(self, r: UsageRecord) -> list[Any]:
        c, t = r.costs, r.tokens
        return [
            record_id(r),
            r.provider.value,
            r.account_id,
            r.api_key_id,
            r.user_id,
            r.project_id,
            r.workspace_id,
            r.model,
            r.operation,
            r.region,
            r.service_tier,
            r.charge_category.value,
            t.input_tokens,
            t.output_tokens,
            t.cache_read_tokens,
            t.cache_write_tokens,
            t.reasoning_tokens,
            t.requests,
            r.seats,
            c.input_cost,
            c.output_cost,
            c.cache_read_cost,
            c.cache_write_cost,
            c.seat_cost,
            c.batch_discount,
            c.tier_adjustment,
            c.other,
            r.billed_cost,
            r.list_cost,
            r.currency,
            r.fx_rate_date,
            r.period_start,
            r.period_end,
            r.ingested_at,
            r.cost_centre,
            r.parent_entity,
            r.allocation_method.value,
            r.source,
            r.completeness.value,
            r.cost_basis.value,
            json.dumps(r.extensions, default=str),
        ]

    def _from_row(self, row: Sequence[Any]) -> UsageRecord:
        d = dict(zip(_COLUMNS, row, strict=True))
        return UsageRecord(
            provider=Provider(d["provider"]),
            account_id=d["account_id"],
            api_key_id=d["api_key_id"],
            user_id=d["user_id"],
            project_id=d["project_id"],
            workspace_id=d["workspace_id"],
            model=d["model"],
            operation=d["operation"],
            region=d["region"],
            service_tier=d["service_tier"],
            charge_category=ChargeCategory(d["charge_category"]),
            tokens=TokenCounts(
                input_tokens=d["input_tokens"],
                output_tokens=d["output_tokens"],
                cache_read_tokens=d["cache_read_tokens"],
                cache_write_tokens=d["cache_write_tokens"],
                reasoning_tokens=d["reasoning_tokens"],
                requests=d["requests"],
            ),
            seats=d["seats"],
            costs=CostComponents(
                input_cost=_dec(d["input_cost"]),
                output_cost=_dec(d["output_cost"]),
                cache_read_cost=_dec(d["cache_read_cost"]),
                cache_write_cost=_dec(d["cache_write_cost"]),
                seat_cost=_dec(d["seat_cost"]),
                batch_discount=_dec(d["batch_discount"]),
                tier_adjustment=_dec(d["tier_adjustment"]),
                other=_dec(d["other_cost"]),
            ),
            billed_cost=_dec(d["billed_cost"]) if d["billed_cost"] is not None else None,
            cost_basis=CostBasis(d["cost_basis"]),
            list_cost=_dec(d["list_cost"]) if d["list_cost"] is not None else None,
            currency=d["currency"],
            fx_rate_date=_as_date(d["fx_rate_date"]),
            period_start=_as_utc(d["period_start"]),
            period_end=_as_utc(d["period_end"]),
            ingested_at=_as_utc(d["ingested_at"]),
            cost_centre=d["cost_centre"],
            parent_entity=d["parent_entity"],
            allocation_method=AllocationMethod(d["allocation_method"]),
            source=d["source"],
            completeness=Completeness(d["completeness"]),
            extensions=json.loads(d["extensions"]) if d["extensions"] else {},
        )


def alert_from_row(row: dict[str, Any]) -> Alert:
    """Rehydrate a stored alert - used by the notifier's retry path."""
    return Alert(
        rule=Rule(row["rule"]),
        severity=Severity(row["severity"]),
        detection_key=(row["provider"], row["credential"]),
        at=_as_utc(row["occurred_at"]),
        observed=_dec(row["observed"]) if row["observed"] is not None else None,
        baseline=_dec(row["baseline"]) if row["baseline"] is not None else None,
        multiple=_dec(row["multiple"]) if row.get("multiple") is not None else None,
        spend_so_far=_dec(row["spend_so_far"]) if row["spend_so_far"] is not None else None,
        projected_24h=_dec(row["projected_24h"]) if row["projected_24h"] is not None else None,
        currency=row["currency"],
        evidence=json.loads(row["evidence"]) if row.get("evidence") else {},
        confidence=row.get("confidence", "high"),
    )


def _dec(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    raise TypeError(f"expected datetime, got {type(value)}")


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else datetime.fromisoformat(str(value)).date()
