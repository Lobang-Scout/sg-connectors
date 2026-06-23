# sg-connectors — project rules

Free, no-auth MCP connectors for Singapore SME data surfaces, by Lobang Scout.
First connector: `sg-company-lookup` (ACRA company/UEN lookup over data.gov.sg).

## Conventions

- **Python:** use `python3.12` explicitly. Server is stdio MCP via FastMCP (`mcp` SDK).
- **Honest scope is a hard rule.** Never return or imply fields the free dataset
  doesn't carry (officers, financials, full address, real-time status). Tests in
  `tests/test_acra.py` guard against inventing paywalled fields — keep them.
- **Snapshot honesty:** every data response includes a note that the source is a
  monthly snapshot, not real-time. Don't strip it.
- **No live network in tests.** Mock `httpx`. Live smoke tests are manual only.
- **Branching:** task branch, no commits to `main` directly. Don't auto-commit.
- No emojis. Keep docs tight.

## Layout

- `uen.py` — UEN format validation (offline, no network).
- `acra.py` — data.gov.sg CKAN `datastore_search` client + `Entity` shape.
- `server.py` — FastMCP server exposing `validate_uen`, `lookup_company`,
  `search_companies`.
- `tests/` — pytest (`asyncio_mode = auto`); network mocked.

## Adding a connector

Each new SG surface (e.g. postal/address, GST registration check) gets its own
client module + tools, with the same honest-scope discipline: document exactly what
the free source returns and what it can't, and add a test that guards the boundary.
