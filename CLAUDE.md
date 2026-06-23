# sg-connectors — project rules

Free, no-auth MCP connectors for Singapore SME data surfaces, by Lobang Scout.
Connectors: `sg-company-lookup` (ACRA company/UEN over data.gov.sg) and `sg-onemap`
(address/postal over OneMap). Packaged so each ships as a `uvx`-installable server.

## Conventions

- **Python:** use `python3.12` explicitly. Servers are stdio MCP via FastMCP (`mcp` SDK).
- **Packaging:** `src/` layout, one console entry point per connector in `pyproject.toml`.
  Installable from git via `uvx --from git+...<repo> <entry>` — no PyPI publish needed.
- **Honest scope is a hard rule.** Never return or imply fields the free dataset
  doesn't carry (officers, financials, full address, real-time status). Tests in
  `tests/test_acra.py` guard against inventing paywalled fields — keep them.
- **Snapshot honesty:** every data response includes a note that the source is a
  monthly snapshot, not real-time. Don't strip it.
- **No live network in tests.** Mock `httpx`. Live smoke tests are manual only.
- **Branching:** task branch, no commits to `main` directly. Don't auto-commit.
- No emojis. Keep docs tight.

## Layout

- `src/sg_connectors/uen.py` — UEN format validation (offline, no network).
- `src/sg_connectors/acra.py` — data.gov.sg CKAN client + `Entity` shape.
- `src/sg_connectors/company_server.py` — FastMCP `sg-company-lookup` server.
- `src/sg_connectors/onemap.py` — OneMap Search client + `Address` shape.
- `src/sg_connectors/onemap_server.py` — FastMCP `sg-onemap` server.
- `tests/` — pytest (`asyncio_mode = auto`, `pythonpath = src`); network mocked.

## Adding a connector

Each new SG surface (e.g. postal/address, GST registration check) gets its own
client module + tools, with the same honest-scope discipline: document exactly what
the free source returns and what it can't, and add a test that guards the boundary.
