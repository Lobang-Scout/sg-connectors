"""sg-company-lookup — MCP server for Singapore company / UEN lookup.

Free, no-auth lookup over ACRA open data (data.gov.sg). Exposes three tools:
  - validate_uen     : check a UEN's format (offline, no network)
  - lookup_company   : exact lookup by UEN
  - search_companies : free-text search by name

HONEST SCOPE: the underlying dataset is a monthly snapshot, not real-time, and
returns only name / type / status / issue-date / street / postal code. It cannot
return officers, financials, shareholders, full address, or live status. Those
require the paid ACRA Business Profile API or a S$5.50 Bizfile profile.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from acra import AcraError, lookup_by_uen, search_by_name
from uen import validate_uen as _validate_uen

mcp = FastMCP("sg-company-lookup")

_SNAPSHOT_NOTE = (
    "Source: ACRA open data via data.gov.sg, refreshed monthly. Not real-time — "
    "recently struck-off or newly registered entities may lag. No officers, "
    "financials, or full address in this free dataset."
)


@mcp.tool()
def validate_uen(uen: str) -> dict:
    """Validate the format of a Singapore UEN (Unique Entity Number).

    Offline check — confirms the string matches one of the three official UEN
    shapes. Does not confirm the entity exists (use lookup_company for that) and
    cannot verify the check letter (ACRA's checksum is undisclosed).
    """
    c = _validate_uen(uen)
    return {"uen": c.uen, "valid": c.valid, "format": c.format, "description": c.description}


@mcp.tool()
async def lookup_company(uen: str) -> dict:
    """Look up a Singapore entity by its exact UEN.

    Returns the registered name, entity type, status, UEN issue date, and partial
    registered address. Returns found=False if no entity matches.
    """
    c = _validate_uen(uen)
    if not c.valid:
        return {"found": False, "error": f"Invalid UEN format. {c.description}"}
    try:
        entity = await lookup_by_uen(uen)
    except AcraError as e:
        return {"found": False, "error": str(e)}
    if entity is None:
        return {"found": False, "note": _SNAPSHOT_NOTE,
                "message": f"No entity with UEN {c.uen} in the current ACRA snapshot."}
    return {"found": True, "entity": entity.to_dict(), "note": _SNAPSHOT_NOTE}


@mcp.tool()
async def search_companies(name: str, limit: int = 10) -> dict:
    """Search Singapore entities by name (free text, partial match).

    Returns up to `limit` matches (max 50). Useful when you have a company name
    but not its UEN. Names are matched against the registered entity name.
    """
    if not (name or "").strip():
        return {"count": 0, "error": "Provide a non-empty name to search."}
    try:
        entities = await search_by_name(name, limit=limit)
    except AcraError as e:
        return {"count": 0, "error": str(e)}
    return {
        "count": len(entities),
        "results": [e.to_dict() for e in entities],
        "note": _SNAPSHOT_NOTE,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
