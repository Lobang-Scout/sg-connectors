# sg-company-lookup

By **Lobang Scout** — practical, evidence-backed connectors for Singapore SMEs.

A free, no-auth **MCP connector** that lets Claude look up Singapore companies by
**UEN** or **name**, over ACRA's open data on [data.gov.sg](https://data.gov.sg).

This is the first entry in `sg-connectors` — closing the gap our evaluation kept
hitting: the surfaces that define a Singapore SME's day mostly have **no connector**.
Company/UEN lookup is the most reusable starting point.

## Tools

| Tool | What it does | Network |
|---|---|---|
| `validate_uen` | Check a UEN's format against the 3 official patterns | No (offline) |
| `lookup_company` | Exact lookup by UEN | Yes |
| `search_companies` | Free-text search by name (partial match) | Yes |

## Honest scope

This connector is built on the **free** ACRA open dataset
(`Entities Registered with ACRA`, data.gov.sg). Be clear about what that means:

**It returns:** UEN, entity name, entity type, registration status, UEN issue date,
street name, postal code, issuance agency.

**It does NOT return** — and no free source does:
- **Real-time status.** The dataset is a **monthly snapshot**. An entity struck off
  yesterday may still show `Registered`. Treat status as *as-of-last-refresh*.
- **Officers, directors, shareholders, financials, paid-up capital, SSIC activity,
  or full registered address.** These live behind the **paid** ACRA Business Profile
  API (Corppass + EIQ subscription) or a **~S$5.50** Bizfile profile purchase.
- **Definitive UEN validation.** ACRA's check-letter algorithm is undisclosed, so
  `validate_uen` confirms *format only*; existence is confirmed by a dataset hit.

For anything statutory or real-time, verify on
[Bizfile](https://www.bizfile.gov.sg). This connector is for fast, free first-pass
lookup and enrichment — not the system of record.

## Install (local clone)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run the server (stdio):
```bash
.venv/bin/python server.py
```

### Wire it into Claude (`.mcp.json`)

```json
{
  "mcpServers": {
    "sg-company-lookup": {
      "command": "/absolute/path/to/sg-connectors/.venv/bin/python",
      "args": ["/absolute/path/to/sg-connectors/server.py"]
    }
  }
}
```

### Optional: raise the rate limit

Without a key, data.gov.sg allows **4 requests / 10s**. A free API key lifts this to
20/10s. Set it before launching Claude:
```bash
export DATAGOV_API_KEY=...
```
Request a key at [guide.data.gov.sg](https://guide.data.gov.sg).

## UEN formats (what `validate_uen` checks)

| Format | Shape | Entity |
|---|---|---|
| A | `nnnnnnnnX` | Business (sole-prop / partnership) |
| B | `yyyynnnnnX` | Local company (`yyyy` = incorporation year) |
| C | `TyyPQnnnnX` | Other entity (prefix T/S/R, `PQ` = 2-letter type) |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Network is mocked in tests — no live calls in CI.

## Data source & licence

Data: ACRA via [data.gov.sg](https://data.gov.sg), under the
[Singapore Open Data Licence](https://data.gov.sg/open-data-licence). This connector
is an independent tool and is not affiliated with or endorsed by ACRA or GovTech.
