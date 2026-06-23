# sg-connectors

By **Lobang Scout** — practical, evidence-backed connectors for Singapore SMEs.

Free, no-auth **MCP connectors** that let Claude reach the Singapore data surfaces an
SME actually uses. Closing the gap our evaluation kept hitting: most of those
surfaces have **no connector**.

| Connector | Server | Source | Auth |
|---|---|---|---|
| **Company / UEN lookup** | `sg-company-lookup` | ACRA open data (data.gov.sg) | None |
| **Address / postal code** | `sg-onemap` | OneMap (SLA) | None (optional free token) |

## Tools

**`sg-company-lookup`**
| Tool | What it does | Network |
|---|---|---|
| `validate_uen` | Check a UEN's format against the 3 official patterns | No (offline) |
| `lookup_company` | Exact lookup by UEN | Yes |
| `search_companies` | Free-text search by name | Yes |

**`sg-onemap`**
| Tool | What it does |
|---|---|
| `lookup_postal_code` | Resolve a 6-digit SG postal code to address + coordinates |
| `search_address` | Free-text address / building / road search |

## Honest scope

These are built on **free** government open data. Be clear about the limits:

**Company / UEN (ACRA open dataset):**
- Returns: UEN, entity name, type, registration status, UEN issue date, street name,
  postal code, issuance agency.
- **Monthly snapshot — not real-time.** A struck-off entity may still show `Registered`.
- **No** officers, directors, shareholders, financials, paid-up capital, SSIC activity,
  or full address. Those need the paid ACRA Business Profile API (Corppass + EIQ) or a
  **~S$5.50** Bizfile profile.
- `validate_uen` confirms *format only* — ACRA's check-letter algorithm is undisclosed.

**Address (OneMap):**
- Singapore addresses only. Returns block, road, building, full address, postal code,
  WGS84 lat/long, and SVY21 x/y.
- The Search API is free; OneMap may require a free token in future (set `ONEMAP_TOKEN`).

For anything statutory or real-time, verify at the source
([Bizfile](https://www.bizfile.gov.sg), [OneMap](https://www.onemap.gov.sg)). These
connectors are for fast, free first-pass lookup — not the system of record.

## Install

### Into Claude via `uvx` (no clone needed)

Add to your `.mcp.json` (or your plugin's). Runs straight from this repo:

```json
{
  "mcpServers": {
    "sg-company-lookup": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Lobang-Scout/sg-connectors", "sg-company-lookup"],
      "env": { "DATAGOV_API_KEY": "${DATAGOV_API_KEY}" }
    },
    "sg-onemap": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Lobang-Scout/sg-connectors", "sg-onemap"]
    }
  }
}
```

### Local clone (development)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/sg-company-lookup    # or: .venv/bin/sg-onemap
```

### Optional: raise the rate limit (company lookup)

Without a key, data.gov.sg allows **4 requests / 10s**. A free API key lifts this to
20/10s. `export DATAGOV_API_KEY=...` before launching Claude. Request a key at
[guide.data.gov.sg](https://guide.data.gov.sg).

## UEN formats (what `validate_uen` checks)

| Format | Shape | Entity |
|---|---|---|
| A | `nnnnnnnnX` | Business (sole-prop / partnership) |
| B | `yyyynnnnnX` | Local company (`yyyy` = incorporation year) |
| C | `TyyPQnnnnX` | Other entity (prefix T/S/R, `PQ` = 2-letter type) |

## Tests

```bash
.venv/bin/python -m pytest -q
```

Network is mocked in tests — no live calls in CI.

## Data sources & licence

- Company data: ACRA via [data.gov.sg](https://data.gov.sg), under the
  [Singapore Open Data Licence](https://data.gov.sg/open-data-licence).
- Address data: [OneMap](https://www.onemap.gov.sg) (Singapore Land Authority).

This connector is an independent tool, not affiliated with or endorsed by ACRA,
SLA, or GovTech. Code under MIT (see `LICENSE`).
