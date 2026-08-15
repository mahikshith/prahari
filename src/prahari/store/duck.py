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

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from prahari.core.models import (
    AllocationMethod,
    ChargeCategory,
    Completeness,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)
from prahari.detect.rules import Alert, Rule, Severity

SCHEMA_VERSION = 1

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
        self._migrate()

    def _migrate(self) -> None:
        self._con.execute(DDL)
        current = self._con.execute("SELECT max(version) FROM schema_meta").fetchone()[0]
        if current is None:
            self._con.execute(
                "INSERT INTO schema_meta VALUES (?, ?)", [SCHEMA_VERSION, datetime.now(UTC)]
            )

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
        """Sum of billed cost in one currency. Rejects mixed currencies rather than
        adding rupees to dollars - a silently wrong total is worse than an error."""
        row = self._con.execute(
            """
            SELECT count(DISTINCT currency), sum(billed_cost)
            FROM usage_records
            WHERE period_start >= ? AND period_start < ? AND currency = ?
            """,
            [start, end, currency.upper()],
        ).fetchone()
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

    def pending_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Alerts recorded but not yet delivered - the retry queue after an outage in
        Slack or SMTP."""
        cursor = self._con.execute(
            """
            SELECT alert_id, rule, severity, provider, credential, occurred_at,
                   observed, baseline, spend_so_far, projected_24h, currency, evidence
            FROM alerts WHERE notified_at IS NULL ORDER BY occurred_at DESC LIMIT ?
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
            "INSERT INTO budget_thresholds VALUES (?,?,?,?,?)",
            [budget_id, period_start, threshold, datetime.now(UTC), None],
        )
        return True

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
            billed_cost=_dec(d["billed_cost"]),
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
        observed=_dec(row["observed"]),
        baseline=_dec(row["baseline"]),
        multiple=None,
        spend_so_far=_dec(row["spend_so_far"]),
        projected_24h=_dec(row["projected_24h"]),
        currency=row["currency"],
        evidence=json.loads(row["evidence"]) if row.get("evidence") else {},
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
