"""sg-onemap — MCP server for Singapore address / postal-code lookup.

Free, low-auth lookup over OneMap (Singapore Land Authority). Exposes two tools:
  - lookup_postal_code : resolve a 6-digit SG postal code to its address
  - search_address     : free-text address / building / road search

HONEST SCOPE: OneMap covers Singapore addresses only. The Search API is free; it
may require a free token in future (set ONEMAP_TOKEN if so). Coordinates are
returned in both WGS84 (lat/long) and SVY21 (x/y metres).
"""

from __future__ import annotations

import re

from mcp.server.fastmcp import FastMCP

from .onemap import OneMapError, search

mcp = FastMCP("sg-onemap")

_SCOPE_NOTE = "Source: OneMap (Singapore Land Authority). Singapore addresses only."
_POSTAL_RE = re.compile(r"^\d{6}$")


@mcp.tool()
async def lookup_postal_code(postal_code: str) -> dict:
    """Resolve a 6-digit Singapore postal code to its address and coordinates.

    Returns the best-matching address (block, road, building, full address,
    lat/long, SVY21 x/y). Returns found=False if the postal code is not in OneMap.
    """
    code = (postal_code or "").strip()
    if not _POSTAL_RE.match(code):
        return {"found": False, "error": "Singapore postal codes are exactly 6 digits."}
    try:
        results = await search(code)
    except OneMapError as e:
        return {"found": False, "error": str(e)}
    # Prefer an exact postal match; fall back to the first result.
    exact = next((a for a in results if a.postal == code), None)
    best = exact or (results[0] if results else None)
    if best is None:
        return {"found": False, "note": _SCOPE_NOTE,
                "message": f"No address found for postal code {code}."}
    return {"found": True, "address": best.to_dict(), "note": _SCOPE_NOTE}


@mcp.tool()
async def search_address(query: str, limit: int = 10) -> dict:
    """Search Singapore addresses by free text (building name, road, or address).

    Returns up to `limit` matches with coordinates. Useful for resolving a partial
    or informal address to a canonical address + postal code.
    """
    if not (query or "").strip():
        return {"count": 0, "error": "Provide a non-empty address or building to search."}
    limit = max(1, min(limit, 50))
    try:
        results = await search(query)
    except OneMapError as e:
        return {"count": 0, "error": str(e)}
    results = results[:limit]
    return {
        "count": len(results),
        "results": [a.to_dict() for a in results],
        "note": _SCOPE_NOTE,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
