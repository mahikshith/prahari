"""GCP billing export connector tests.

Two properties matter more than the rest and are the reason most of these exist:

  1. **Net cost = cost + credits.** Credits are negative amounts in a repeated field.
     Reporting gross overstates the bill by every discount the customer negotiated -
     the first number they will check us against.
  2. **Non-AI services must not produce token counts.** Cloud Run seconds and BigQuery
     bytes are real usage but not tokens, and coercing them would corrupt every
     token-denominated report.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from prahari.connectors.base import ProviderConfig
from prahari.connectors.gcp import (
    GCPBillingConnector,
    _model_from_sku,
    classify,
)
from prahari.core.models import ChargeCategory, Completeness, CostBasis, Provider

START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
END = START + timedelta(hours=2)
LATE_EXPORT = END + timedelta(hours=1)


def row(**overrides) -> dict:
    base = {
        "hour": START,
        "service": "Vertex AI",
        "sku": "Gemini 2.5 Pro Input Tokens",
        "project_id": "robotics-prod",
        "project_name": "Robotics Production",
        "region": "asia-south1",
        "currency": "INR",
        "cost_type": "regular",
        "invoice_month": "202606",
        "gross_cost": 1000.0,
        "credit_amount": 0.0,
        "usage_amount": 5_000_000,
        "usage_unit": "tokens",
        "pricing_unit": "1M tokens",
        "last_export_time": LATE_EXPORT,
        "cost_centre": "cc-robotics",
    }
    base.update(overrides)
    return base


class FakeQueryJob:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def result(self, *, timeout=None, retry=None, job_retry=None):
        self.result_options = {"timeout": timeout, "retry": retry, "job_retry": job_retry}
        return iter(self._rows)


class FakeBQClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.last_params: dict = {}

    def query(self, sql, job_config=None, **kwargs):
        if job_config is not None and getattr(job_config, "query_parameters", None):
            self.last_params = {p.name: p.value for p in job_config.query_parameters}
        self.last_sql = sql
        self.last_options = kwargs
        self.last_job_config = job_config
        self.last_job = FakeQueryJob(self._rows)
        return self.last_job


def connector(rows: list[dict], **kw) -> GCPBillingConnector:
    return GCPBillingConnector(
        ProviderConfig(
            provider=Provider.GCP_VERTEX,
            account_id="billing-acct-1",
            extra={
                "billing_project": "proj",
                "billing_dataset": "billing",
                "billing_table": "gcp_billing_export_v1_XXXX",
            },
        ),
        client=FakeBQClient(rows),
        **kw,
    )


class TestCostArithmetic:
    @pytest.mark.asyncio
    async def test_credits_are_subtracted_from_billed_cost(self):
        """The single most consequential line in this connector."""
        result = await connector([row(gross_cost=1000.0, credit_amount=-250.0)]).fetch(START, END)

        rec = result.records[0]
        assert rec.billed_cost == Decimal("750.0")
        assert rec.list_cost is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cost_type, category", [
        ("regular", ChargeCategory.USAGE),
        ("tax", ChargeCategory.TAX),
        ("adjustment", ChargeCategory.ADJUSTMENT),
        ("rounding_error", ChargeCategory.ADJUSTMENT),
    ])
    async def test_preserves_charge_type_and_invoice_month(self, cost_type, category):
        result = await connector([row(cost_type=cost_type, invoice_month="202607")]).fetch(
            START, END
        )
        rec = result.records[0]
        assert rec.charge_category is category
        assert rec.extensions["cost_type"] == cost_type
        assert rec.extensions["invoice_month"] == "202607"
        if category is not ChargeCategory.USAGE:
            assert rec.tokens.total_tokens == 0

    @pytest.mark.asyncio
    async def test_rejects_unknown_charge_type(self):
        with pytest.raises(ValueError, match="unsupported GCP cost_type"):
            await connector([row(cost_type="unexpected")]).fetch(START, END)

    @pytest.mark.asyncio
    async def test_credit_is_visible_as_its_own_component(self):
        """Customers want to see the discount, not only its effect."""
        result = await connector([row(gross_cost=1000.0, credit_amount=-250.0)]).fetch(START, END)
        assert result.records[0].costs.tier_adjustment == Decimal("-250.0")

    @pytest.mark.asyncio
    async def test_preserves_billing_account_currency(self):
        """Indian billing accounts export in INR. Assuming USD would be wrong by ~84x."""
        result = await connector([row(currency="INR")]).fetch(START, END)
        assert result.records[0].currency == "INR"


class TestServiceCoverage:
    """One connector, every GCP service - the unified-platform North Star arriving
    free alongside the AI wedge."""

    @pytest.mark.asyncio
    async def test_covers_vertex_bigquery_and_cloud_run_in_one_pull(self):
        rows = [
            row(service="Vertex AI", sku="Gemini 2.5 Pro Input Tokens"),
            row(
                service="BigQuery",
                sku="Analysis",
                usage_amount=2 * 1024**4,
                usage_unit="bytes",
            ),
            row(
                service="Cloud Run",
                sku="CPU Allocation Time",
                usage_amount=7200,
                usage_unit="seconds",
            ),
        ]
        result = await connector(rows).fetch(START, END)

        assert len(result.records) == 3
        assert {r.extensions["service"] for r in result.records} == {
            "Vertex AI",
            "BigQuery",
            "Cloud Run",
        }

    def test_classifies_services_into_ai_data_and_compute(self):
        assert classify("Vertex AI") == "ai"
        assert classify("BigQuery") == "data"
        assert classify("Cloud Run") == "compute"
        assert classify("Cloud Armor") == "other"

    @pytest.mark.asyncio
    async def test_bigquery_reports_tib_scanned(self):
        result = await connector(
            [row(service="BigQuery", sku="Analysis", usage_amount=2 * 1024**4, usage_unit="bytes")]
        ).fetch(START, END)
        assert result.records[0].extensions["bq_tib_scanned"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_cloud_run_reports_vcpu_hours(self):
        result = await connector(
            [
                row(
                    service="Cloud Run",
                    sku="CPU Allocation Time",
                    usage_amount=7200,
                    usage_unit="vCPU-seconds",
                )
            ]
        ).fetch(START, END)
        assert result.records[0].extensions["run_vcpu_hours"] == pytest.approx(2.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("unit, amount", [
        ("byte-seconds", 1024**3 * 3600),
        ("gibibyte second", 3600),
    ])
    async def test_cloud_run_converts_memory_usage_to_gib_hours(self, unit, amount):
        result = await connector([row(
            service="Cloud Run", sku="Memory Allocation Time", usage_unit=unit, usage_amount=amount,
        )]).fetch(START, END)
        assert result.records[0].extensions["run_gib_hours"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_bigquery_storage_is_not_reported_as_query_bytes(self):
        result = await connector([row(
            service="BigQuery", sku="Storage", usage_unit="byte-seconds", usage_amount=1024**4,
        )]).fetch(START, END)
        assert "bq_tib_scanned" not in result.records[0].extensions


class TestTokenMapping:
    @pytest.mark.asyncio
    async def test_input_output_and_cached_tokens_are_distinguished(self):
        rows = [
            row(sku="Gemini 2.5 Pro Input Tokens", usage_amount=1000),
            row(sku="Gemini 2.5 Pro Output Tokens", usage_amount=200),
            row(sku="Gemini 2.5 Pro Cached Input Tokens", usage_amount=500),
        ]
        result = await connector(rows).fetch(START, END)

        assert result.records[0].tokens.input_tokens == 1000
        assert result.records[1].tokens.output_tokens == 200
        assert result.records[2].tokens.cache_read_tokens == 500

    @pytest.mark.asyncio
    async def test_non_ai_services_produce_no_tokens(self):
        """Cloud Run seconds are real usage, but they are not tokens."""
        result = await connector(
            [row(service="Cloud Run", sku="CPU Allocation Time", usage_unit="seconds")]
        ).fetch(START, END)

        assert result.records[0].tokens.total_tokens == 0
        assert result.records[0].model is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("service, sku, unit", [
        ("Cloud Translation API", "Translation characters", "characters"),
        ("Vertex AI", "Gemini Context Cache Storage", "token-hours"),
        ("Vertex AI", "Gemini Context Cache Storage", "tokens"),
    ])
    async def test_characters_and_cache_storage_are_not_inference_tokens(self, service, sku, unit):
        result = await connector([row(service=service, sku=sku, usage_unit=unit)]).fetch(START, END)
        assert result.records[0].tokens.total_tokens == 0
        assert result.records[0].extensions["usage_amount"] == 5_000_000
        assert result.records[0].extensions["usage_unit"] == unit

    def test_model_extraction_returns_none_on_unrecognised_sku(self):
        """SKU descriptions are human prose and change without notice. A wrong model
        attribution silently misprices and would make MODEL_ESCALATION fire on a
        rename rather than an attack."""
        assert _model_from_sku("Gemini 2.5 Pro Input Tokens") == "Gemini 2.5 Pro"
        assert _model_from_sku("Network Internet Egress") is None
        assert _model_from_sku("") is None


class TestCompleteness:
    @pytest.mark.asyncio
    async def test_window_is_incomplete_when_export_lags(self):
        """The export lags 4-24h with no guarantee. Presenting a total that will
        change tomorrow is how a finance buyer stops trusting us."""
        result = await connector([row(last_export_time=START)]).fetch(START, END)

        assert result.is_complete is False
        assert result.warnings and "not settled" in result.warnings[0]
        assert result.records[0].completeness is Completeness.PARTIAL
        assert result.records[0].cost_basis is CostBasis.PROVIDER_REPORTED

    @pytest.mark.asyncio
    async def test_later_export_arrival_does_not_prove_window_complete(self):
        result = await connector([row(last_export_time=LATE_EXPORT)]).fetch(START, END)
        assert result.is_complete is False
        assert result.records[0].completeness is Completeness.PARTIAL


class TestQueryConstruction:
    @pytest.mark.asyncio
    async def test_passes_window_as_bound_parameters(self):
        conn = connector([row()])
        await conn.fetch(START, END)
        assert conn._client.last_params["start"] == START
        assert conn._client.last_params["end"] == END

    @pytest.mark.asyncio
    async def test_prunes_partitions(self):
        """Billing export tables run to terabytes. An unpruned scan would be a
        memorable way to introduce a cost-control product."""
        conn = connector([row()])
        await conn.fetch(START, END)
        assert "_PARTITIONTIME >= TIMESTAMP_SUB(@start" in conn._client.last_sql

    @pytest.mark.asyncio
    async def test_partition_filter_does_not_exclude_late_exports(self):
        conn = connector([row(last_export_time=END + timedelta(days=30))])
        result = await conn.fetch(START, END)
        assert "_PARTITIONTIME <" not in conn._client.last_sql
        assert len(result.records) == 1
        assert result.is_complete is False

    @pytest.mark.asyncio
    async def test_buckets_hourly_not_daily(self):
        conn = connector([row()])
        await conn.fetch(START, END)
        assert "TIMESTAMP_TRUNC(usage_start_time, HOUR)" in conn._client.last_sql

    @pytest.mark.asyncio
    async def test_keeps_invoice_and_charge_type_in_query_grain(self):
        conn = connector([row()])
        await conn.fetch(START, END)
        sql = conn._client.last_sql
        assert "invoice.month" in sql
        assert "cost_type, invoice_month" in sql.split("GROUP BY", 1)[1]

    @pytest.mark.asyncio
    async def test_attributes_to_usage_time_not_export_time(self):
        """Using export_time silently backdates spend into whichever window Google
        happened to deliver it in."""
        conn = connector([row()])
        await conn.fetch(START, END)
        assert "WHERE usage_start_time >=" in conn._client.last_sql


class TestAllocation:
    @pytest.mark.asyncio
    async def test_reads_cost_centre_from_project_label(self):
        result = await connector([row(cost_centre="cc-robotics")]).fetch(START, END)
        assert result.records[0].cost_centre == "cc-robotics"

    @pytest.mark.asyncio
    async def test_no_caller_identity_available(self):
        """The billing export knows project, service and SKU - never who called.
        Credential-level detection on GCP requires Cloud Audit Logs (ASSUMPTIONS A11).
        Asserting this so the limitation cannot be forgotten silently."""
        result = await connector([row()]).fetch(START, END)
        rec = result.records[0]

        assert rec.api_key_id is None
        # Project is therefore the finest detection grain this source supports.
        assert rec.detection_key == ("gcp_vertex", "robotics-prod")


class TestConfiguration:
    @pytest.mark.asyncio
    async def test_missing_table_config_raises_clearly(self, monkeypatch):
        for var in ("GCP_BILLING_PROJECT", "GCP_BILLING_DATASET", "GCP_BILLING_TABLE"):
            monkeypatch.delenv(var, raising=False)

        conn = GCPBillingConnector(
            ProviderConfig(provider=Provider.GCP_VERTEX, account_id="acct"),
            client=FakeBQClient([]),
        )
        with pytest.raises(RuntimeError, match="GCP_BILLING_PROJECT"):
            await conn.fetch(START, END)

    @pytest.mark.asyncio
    async def test_rejects_naive_datetimes(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector([]).fetch(datetime(2026, 6, 1), datetime(2026, 6, 2))


class TestQueryDeadlines:
    @pytest.mark.asyncio
    async def test_submit_and_result_waits_are_bounded_without_automatic_retries(self):
        conn = connector([row()])
        await conn.fetch(START, END)
        assert conn._client.last_options == {"timeout": 15, "retry": None, "job_retry": None}
        assert conn._client.last_job.result_options == {
            "timeout": 40, "retry": None, "job_retry": None,
        }
        assert conn._client.last_job_config.job_timeout_ms == "40000"

    @pytest.mark.asyncio
    async def test_timed_out_query_is_not_reported_as_empty_or_complete(self, monkeypatch):
        def timeout_result(self, *, timeout, retry, job_retry):
            assert timeout == 40
            raise TimeoutError("query wait timed out")

        monkeypatch.setattr(FakeQueryJob, "result", timeout_result)
        with pytest.raises(TimeoutError, match="query wait timed out"):
            await connector([row()]).fetch(START, END)

    @pytest.mark.asyncio
    async def test_credential_dry_run_submit_is_bounded(self):
        conn = connector([])
        assert await conn.verify_credentials()
        assert conn._client.last_options == {"timeout": 15, "retry": None, "job_retry": None}
