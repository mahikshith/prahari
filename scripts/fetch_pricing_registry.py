"""Vendor the LiteLLM model price registry.

Downloads `model_prices_and_context_window.json` at a PINNED COMMIT SHA, verifies it,
and writes it plus a checksum into src/prahari/pricing/vendor/.

Why not just `pip install litellm`:
    The LiteLLM PyPI package suffered a confirmed supply-chain attack in March 2026,
    shipping backdoored builds carrying a credential-stealing payload. We handle AI
    admin credentials — we are the exact target. We take the data, never the code.

Updating the pin:
    1. Review the upstream diff between PINNED_SHA and the new commit.
    2. Update PINNED_SHA below.
    3. Run this script.
    4. Commit the JSON, the .sha256, and the diff — a pricing change moves customer
       invoices, so it gets reviewed like any other code change.

Usage:
    python scripts/fetch_pricing_registry.py
    python scripts/fetch_pricing_registry.py --sha <commit>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

# Pinned deliberately. Never point this at a branch name - a branch means whatever
# upstream pushes lands in our cost calculations unreviewed.
PINNED_SHA = "4ea5749642de69e86e9414b1557eb8d00660c63c"  # 2026-08-14, 2409 priced models

RAW_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/{sha}/"
    "model_prices_and_context_window.json"
)

VENDOR_DIR = Path(__file__).resolve().parents[1] / "src" / "prahari" / "pricing" / "vendor"
JSON_PATH = VENDOR_DIR / "model_prices.json"
SHA_PATH = VENDOR_DIR / "model_prices.sha256"
PROVENANCE_PATH = VENDOR_DIR / "PROVENANCE.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", default=PINNED_SHA, help="Commit SHA to pin to")
    args = parser.parse_args()

    if args.sha in {"main", "master", "HEAD"}:
        print(
            f"WARNING: fetching from branch '{args.sha}', not a pinned commit.\n"
            "         Acceptable for the first fetch only. Record the resolved SHA in\n"
            "         PINNED_SHA immediately afterwards.\n",
            file=sys.stderr,
        )

    url = RAW_URL.format(sha=args.sha)
    print(f"Fetching {url}")

    try:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"ERROR: fetch failed: {exc}", file=sys.stderr)
        return 1

    payload = resp.content

    # Validate before we trust it: this file drives every cost number we report.
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f"ERROR: not valid JSON: {exc}", file=sys.stderr)
        return 1

    priced = sum(
        1
        for k, v in data.items()
        if k != "sample_spec" and isinstance(v, dict) and v.get("input_cost_per_token")
    )
    if priced < 100:
        print(
            f"ERROR: only {priced} priced models found — expected 400+. "
            "Refusing to vendor a suspect file.",
            file=sys.stderr,
        )
        return 1

    digest = hashlib.sha256(payload).hexdigest()

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_bytes(payload)
    SHA_PATH.write_text(f"{digest}  model_prices.json\n", encoding="utf-8")
    PROVENANCE_PATH.write_text(
        "# Provenance\n\n"
        "`model_prices.json` is vendored from LiteLLM (MIT).\n\n"
        f"- Source: `{url}`\n"
        f"- Pinned SHA: `{args.sha}`\n"
        f"- SHA-256: `{digest}`\n"
        f"- Priced models: {priced}\n\n"
        "Data file only. **The `litellm` PyPI package must never be installed** — it\n"
        "shipped a credential-stealing supply-chain payload in March 2026, and this\n"
        "product handles AI admin credentials.\n\n"
        "Refresh with `python scripts/fetch_pricing_registry.py --sha <commit>` and\n"
        "review the diff: pricing changes move customer invoices.\n",
        encoding="utf-8",
    )

    print(f"OK  {priced} priced models")
    print(f"    {JSON_PATH}")
    print(f"    sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
