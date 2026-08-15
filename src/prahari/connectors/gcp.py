"""GCP connector - BigQuery Cloud Billing export.

Covers **every GCP service in one connector**, because the billing export table
already contains all of them: Vertex AI (the incident surface), BigQuery, Cloud Run,
Compute, Storage, egress. This is the first place the unified-platform North Star and
the AI wedge stop being in tension - one query, and cloud coverage arrives essentially
free alongside the AI coverage we actually need.

Two things about this data source that shape everything below:

**1. It is slow.** Export latency is typically 4-24h and Google makes no freshness
guarantee. That is fine for allocation, chargeback and reconciliation - and useless
for detection. Sub-hour credential-abuse detection on GCP needs Cloud Audit Logs, not
this table. Do not confuse the two jobs.

**2. It has no caller identity.** The billing export knows project, service, SKU and
resource - never *who* called. So the finest detection grain available here is the
project, not the service account. Credential-level detection on GCP requires joining
Cloud Audit Logs (`protoPayload.authenticationInfo.principalEmail`, `callerIp`), which
is a separate connector. See ASSUMPTIONS.md A11.

Cost arithmetic that is easy to get wrong and expensive to get wrong:
    net cost = cost + SUM(credits.amount)
Credits are stored as negative amounts in a repeated field. Reporting `cost` alone
overstates the bill by every committed-use and sustained-use discount the customer
negotiated - which is precisely the number they will check us against first.

NOT YET EXERCISED against a live billing export - see ASSUMPTIONS.md A8.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from prahari.connectors.base import Connector, FetchResult, ProviderConfig
from prahari.core.models import (
    ChargeCategory,
    Completeness,
    CostComponents,
    Provider,
    TokenCounts,
    UsageRecord,
)
from prahari.core.money import parse_money

# --- service taxonomy ---------------------------------------------------------
# Drives the AI-vs-cloud split in reporting. The wedge is AI; the North Star is
# everything. Both are served from the same rows, so the classification lives here
# rather than in a downstream report that would have to re-derive it.

AI_SERVICES = frozenset(
    {
        "Vertex AI",
        "Generative Language API",
        "AI Platform",
        "Cloud Natural Language",
        "Cloud Vision API",
        "Speech-to-Text",
        "Text-to-Speech",
        "Cloud Translation API",
        "Document AI",
        "Notebooks",
    }
)

DATA_SERVICES = frozenset({"BigQuery", "BigQuery Reservation API", "BigQuery Storage API"})
COMPUTE_SERVICES = frozenset(
    {"Cloud Run", "Cloud Run Functions", "Compute Engine", "Kubernetes Engine", "App Engine"}
)


def classify(service: str) -> str:
    if service in AI_SERVICES:
        return "ai"
    if service in DATA_SERVICES:
        return "data"
    if service in COMPUTE_SERVICES:
        return "compute"
    return "other"


# --- query --------------------------------------------------------------------
# Hourly buckets. Daily would be cheaper to scan but throws away the only temporal
# resolution this source has, and we would never get it back.
#
# `usage_start_time` rather than `export_time`: we want when consumption happened,
# not when Google told us about it. Using export_time silently backdates spend into
# whichever window the export happened to land in.

USAGE_QUERY = """
SELECT
  TIMESTAMP_TRUNC(usage_start_time, HOUR)      AS hour,
  service.description                          AS service,
  sku.description                              AS sku,
  project.id                                   AS project_id,
  project.name                                 AS project_name,
  location.region                              AS region,
  currency                                     AS currency,
  SUM(cost)                                    AS gross_cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credit_amount,
  SUM(usage.amount)                            AS usage_amount,
  ANY_VALUE(usage.unit)                        AS usage_unit,
  ANY_VALUE(usage.pricing_unit)                AS pricing_unit,
  MAX(export_time)                             AS last_export_time,
  ARRAY_AGG(DISTINCT lbl.value IGNORE NULLS LIMIT 1)[SAFE_OFFSET(0)] AS cost_centre
FROM `{table}`
LEFT JOIN UNNEST(project.labels) AS lbl ON lbl.key = @cost_centre_label
WHERE usage_start_time >= @start
  AND usage_start_time <  @end
  -- Partition pruning. The export table is partitioned on _PARTITIONTIME and a
  -- customer's is measured in TB; without this the first query is a bill of its own,
  -- which would be a memorable way to introduce a cost-control product.
  AND _PARTITIONTIME >= TIMESTAMP_SUB(@start, INTERVAL 2 DAY)
  AND _PARTITIONTIME <  TIMESTAMP_ADD(@end, INTERVAL 2 DAY)
GROUP BY hour, service, sku, project_id, project_name, region, currency
HAVING gross_cost != 0 OR credit_amount != 0
ORDER BY hour
"""


class GCPBillingConnector(Connector):
    """Cloud Billing export -> UsageRecord, across all GCP services."""

    provider = Provider.GCP_VERTEX

    def __init__(
        self,
        config: ProviderConfig,
        client: Any | None = None,
        cost_centre_label: str = "cost-centre",
    ) -> None:
        super().__init__(config)
        self._client = client
        self._cost_centre_label = cost_centre_label

    # --- plumbing -------------------------------------------------------------

    def _table(self) -> str:
        extra = self.config.extra or {}
        project = extra.get("billing_project") or os.environ.get("GCP_BILLING_PROJECT", "")
        dataset = extra.get("billing_dataset") or os.environ.get("GCP_BILLING_DATASET", "")
        table = extra.get("billing_table") or os.environ.get("GCP_BILLING_TABLE", "")
        if not (project and dataset and table):
            raise RuntimeError(
                "GCP billing export not configured. Set GCP_BILLING_PROJECT, "
                "GCP_BILLING_DATASET and GCP_BILLING_TABLE (typically "
                "gcp_billing_export_v1_<BILLING_ACCOUNT_ID>)."
            )

        # A table identifier cannot be a bound parameter in BigQuery, so it is
        # interpolated into the SQL. That makes it an injection sink, and it will not
        # always come from a trusted env var - in the multi-tenant control plane it
        # arrives from per-tenant configuration. Validate as an allowlist.
        return ".".join(
            (
                _validate_identifier(project, "billing_project", allow_domain=True),
                _validate_identifier(dataset, "billing_dataset"),
                _validate_identifier(table, "billing_table"),
            )
        )

    def _bq(self):
        if self._client is not None:
            return self._client
        from google.cloud import bigquery  # imported lazily: optional [gcp] extra

        return bigquery.Client()

    # --- fetch ----------------------------------------------------------------

    async def fetch(self, start: datetime, end: datetime) -> FetchResult:
        _require_utc(start, end)

        from google.cloud import bigquery

        client = self._bq()
        job = client.query(
            USAGE_QUERY.format(table=self._table()),
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("start", "TIMESTAMP", start),
                    bigquery.ScalarQueryParameter("end", "TIMESTAMP", end),
                    bigquery.ScalarQueryParameter(
                        "cost_centre_label", "STRING", self._cost_centre_label
                    ),
                ]
            ),
        )

        now = datetime.now(UTC)
        records: list[UsageRecord] = []
        warnings: list[str] = []
        latest_export: datetime | None = None

        for row in job:
            record = self._to_record(row, now)
            records.append(record)
            export_time = _as_utc(row["last_export_time"])
            if export_time and (latest_export is None or export_time > latest_export):
                latest_export = export_time

        # The export lags by hours and Google guarantees nothing. If it has not caught
        # up past our window end, the window is still filling - say so rather than
        # presenting a total that will change tomorrow.
        complete = latest_export is not None and latest_export >= end
        if not complete:
            warnings.append(
                f"billing export has not settled past {end:%Y-%m-%d %H:%M}Z "
                f"(latest export {latest_export:%Y-%m-%d %H:%M}Z)"
                if latest_export
                else "no export rows in window"
            )

        return FetchResult(
            records=records,
            window_start=start,
            window_end=end,
            is_complete=complete,
            warnings=warnings or None,
        )

    def _to_record(self, row: Any, now: datetime) -> UsageRecord:
        service = row["service"] or "Unknown"
        sku = row["sku"] or ""
        category = classify(service)

        # BigQuery FLOAT64 can legitimately hold NaN and Infinity. Parsed, not cast:
        # an infinite cost compares as greater than every budget limit and would drive
        # HARD_STOP revocation against production. See core/money.py.
        gross = parse_money(row["gross_cost"], field="gross_cost", default=Decimal(0))
        credits = parse_money(row["credit_amount"], field="credit_amount", default=Decimal(0))
        net = gross + credits

        hour = _as_utc(row["hour"])
        tokens = _tokens_from_usage(row, category, sku)

        return UsageRecord(
            provider=Provider.GCP_VERTEX,
            account_id=self.config.account_id,
            # No caller identity in the billing export - the project IS the finest
            # grain available here. Credential-level detection needs audit logs.
            api_key_id=None,
            project_id=row["project_id"],
            model=_model_from_sku(sku) if category == "ai" else None,
            operation=sku or None,
            region=row["region"],
            charge_category=ChargeCategory.USAGE,
            tokens=tokens,
            costs=CostComponents(
                other=gross,
                # Credits ride as a separate component so a customer can see their
                # discount rather than only its effect.
                tier_adjustment=credits,
            ),
            billed_cost=net,
            list_cost=gross,
            currency=(row["currency"] or "USD").upper(),
            period_start=hour,
            period_end=hour.replace(minute=59, second=59),
            ingested_at=now,
            cost_centre=row["cost_centre"],
            source="gcp:bigquery_billing_export",
            completeness=Completeness.FINAL,
            extensions={
                "service": service,
                "sku": sku,
                "service_category": category,
                "project_name": row["project_name"],
                "usage_amount": float(row["usage_amount"] or 0),
                "usage_unit": row["usage_unit"],
                "pricing_unit": row["pricing_unit"],
                # Unit economics the FinOps buyer actually asks for. Kept as raw
                # usage + unit rather than pre-computed, because "cost per TB
                # scanned" and "cost per vCPU-second" are different questions and
                # only the caller knows which one is being asked.
                **_unit_economics(row, service),
            },
        )

    async def verify_credentials(self) -> bool:
        """Confirms both that credentials work and that the export table is readable -
        two separate failure modes a customer will otherwise hit at 3am."""
        from google.cloud import bigquery

        try:
            client = self._bq()
            job = client.query(
                f"SELECT 1 FROM `{self._table()}` LIMIT 1",
                job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
            )
            return job is not None
        except Exception:
            return False


# --- identifier validation ----------------------------------------------------

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,1024}$")
_DOMAIN_SCOPED = re.compile(r"^[A-Za-z0-9.-]{1,255}:[A-Za-z0-9_-]{1,63}$")
"""Legacy domain-scoped GCP projects look like `example.com:my-project`."""


def _validate_identifier(value: str, field: str, *, allow_domain: bool = False) -> str:
    """Allowlist a BigQuery identifier before it is interpolated into SQL.

    Table names cannot be bound parameters, so this is the only defence. Rejecting
    anything outside `[A-Za-z0-9_-]` blocks backticks, quotes, semicolons, whitespace
    and comment markers - the whole injection vocabulary - without needing to reason
    about BigQuery's escaping rules.
    """
    value = value.strip()
    if _IDENTIFIER.match(value):
        return value
    if allow_domain and _DOMAIN_SCOPED.match(value):
        return value
    raise ValueError(
        f"{field} is not a valid BigQuery identifier: {value!r}. "
        "Only letters, digits, underscores and hyphens are permitted."
    )


# --- SKU interpretation -------------------------------------------------------


def _model_from_sku(sku: str) -> str | None:
    """Best-effort model name from a Vertex SKU description.

    GCP SKUs read like 'Gemini 2.5 Pro Input Tokens' - human prose, not identifiers,
    and the wording changes without notice. Returning None on an unrecognised shape
    is correct: a wrong model attribution silently misprices, and MODEL_ESCALATION
    would then fire on a rename rather than on an attack.
    """
    if not sku:
        return None
    lowered = sku.lower()
    for family in ("gemini", "claude", "llama", "mistral", "imagen", "gemma"):
        if family in lowered:
            head = sku.split(" Input")[0].split(" Output")[0].split(" - ")[0]
            return head.strip() or None
    return None


def _tokens_from_usage(row: Any, category: str, sku: str) -> TokenCounts:
    """Map Vertex token SKUs onto TokenCounts.

    Only AI rows produce token counts. Cloud Run seconds and BigQuery bytes are real
    usage but not tokens, and forcing them into this shape would make every
    token-denominated report wrong.
    """
    if category != "ai":
        return TokenCounts()

    unit = (row["usage_unit"] or "").lower()
    if "token" not in unit and "character" not in unit:
        return TokenCounts()

    amount = int(row["usage_amount"] or 0)
    lowered = sku.lower()
    if "output" in lowered:
        return TokenCounts(output_tokens=amount)
    if "cached" in lowered or "context cach" in lowered:
        return TokenCounts(cache_read_tokens=amount)
    return TokenCounts(input_tokens=amount)


def _unit_economics(row: Any, service: str) -> dict[str, Any]:
    """Service-specific denominators for cost-per-unit reporting.

    BigQuery and Cloud Run are the two services customers most want unit economics on
    after AI - BigQuery because a single bad query can cost more than a month of
    inference, Cloud Run because it is where request-level cost attribution lives.
    """
    amount = float(row["usage_amount"] or 0)
    unit = (row["usage_unit"] or "").lower()

    if service.startswith("BigQuery"):
        if "byte" in unit:
            return {"bq_tib_scanned": amount / (1024**4)}
        if "second" in unit:
            return {"bq_slot_hours": amount / 3600}
    elif service.startswith("Cloud Run"):
        if "cpu" in unit or "vcpu" in unit:
            return {"run_vcpu_hours": amount / 3600}
        if "byte-second" in unit or "gibibyte second" in unit:
            return {"run_gib_hours": amount / 3600}
        if "request" in unit:
            return {"run_requests": amount}
    return {}


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return None


def _require_utc(*values: datetime) -> None:
    for v in values:
        if v.tzinfo is None:
            raise ValueError("fetch window must be timezone-aware UTC")
