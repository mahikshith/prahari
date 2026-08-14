# Provenance

`model_prices.json` is vendored from LiteLLM (MIT).

- Source: `https://raw.githubusercontent.com/BerriAI/litellm/4ea5749642de69e86e9414b1557eb8d00660c63c/model_prices_and_context_window.json`
- Pinned SHA: `4ea5749642de69e86e9414b1557eb8d00660c63c`
- SHA-256: `e7c0872654c7af4adc8a2b52b4a10a5e70e88e8e9c119f78c52d18ec8e1bd616`
- Priced models: 2427

Data file only. **The `litellm` PyPI package must never be installed** — it
shipped a credential-stealing supply-chain payload in March 2026, and this
product handles AI admin credentials.

Refresh with `python scripts/fetch_pricing_registry.py --sha <commit>` and
review the diff: pricing changes move customer invoices.
