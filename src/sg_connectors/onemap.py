"""Thin client for the OneMap (Singapore Land Authority) Search API.

Free address / postal-code lookup. The Search endpoint historically works with no
auth; OneMap is moving toward an optional free token, so we send one if
ONEMAP_TOKEN is set but never require it. SG addresses only.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

import httpx

SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


@dataclass
class Address:
    search_value: str  # SEARCHVAL — the matched name/address
    block: str
    road_name: str
    building: str
    address: str
    postal: str
    latitude: str
    longitude: str
    x: str  # SVY21 easting (metres)
    y: str  # SVY21 northing (metres)

    @classmethod
    def from_record(cls, r: dict) -> "Address":
        return cls(
            search_value=r.get("SEARCHVAL", ""),
            block=r.get("BLK_NO", ""),
            road_name=r.get("ROAD_NAME", ""),
            building=r.get("BUILDING", ""),
            address=r.get("ADDRESS", ""),
            postal=r.get("POSTAL", ""),
            latitude=r.get("LATITUDE", ""),
            longitude=r.get("LONGITUDE", ""),
            x=r.get("X", ""),
            y=r.get("Y", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class OneMapError(RuntimeError):
    """Raised on a non-recoverable API problem (with a user-facing message)."""


def _headers() -> dict:
    token = os.environ.get("ONEMAP_TOKEN")
    return {"Authorization": token} if token else {}


async def search(query: str, page: int = 1) -> list[Address]:
    """Search OneMap for an address, building, or postal code. Returns matches."""
    params = {
        "searchVal": query.strip(),
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": max(1, page),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=_headers())
    except httpx.HTTPError as e:
        raise OneMapError(f"Could not reach OneMap: {e}") from e

    if resp.status_code == 429:
        raise OneMapError("Rate limited by OneMap. Retry shortly.")
    if resp.status_code == 401:
        raise OneMapError(
            "OneMap rejected the request (401). The Search API may now require a "
            "free token — set ONEMAP_TOKEN (see onemap.gov.sg/apidocs/authentication)."
        )
    if resp.status_code != 200:
        raise OneMapError(f"OneMap returned HTTP {resp.status_code}.")

    body = resp.json()
    return [Address.from_record(r) for r in body.get("results", [])]
