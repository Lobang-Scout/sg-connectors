"""Thin client for the ACRA "Entities Registered with ACRA" open dataset.

Source: data.gov.sg CKAN datastore_search API. Free, no auth required (an optional
API key lifts the rate limit). The dataset is a MONTHLY snapshot — it is not
real-time, and it carries only a thin set of fields. See README "Honest scope".
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import httpx

# "Entities Registered with ACRA" — the consolidated dataset.
RESOURCE_ID = "d_3f960c10fed6145404ca7b821f263b87"
BASE_URL = "https://data.gov.sg/api/action/datastore_search"

# Fields the free dataset actually returns (anything else is paywalled at ACRA).
_FIELDS = [
    "uen",
    "entity_name",
    "entity_type_desc",
    "uen_status_desc",
    "uen_issue_date",
    "issuance_agency_desc",
    "reg_street_name",
    "reg_postal_code",
]


@dataclass
class Entity:
    uen: str
    entity_name: str
    entity_type: str
    status: str
    uen_issue_date: str
    issuance_agency: str
    street_name: str
    postal_code: str

    @classmethod
    def from_record(cls, r: dict) -> "Entity":
        return cls(
            uen=r.get("uen", ""),
            entity_name=r.get("entity_name", ""),
            entity_type=r.get("entity_type_desc", ""),
            status=r.get("uen_status_desc", ""),
            uen_issue_date=r.get("uen_issue_date", ""),
            issuance_agency=r.get("issuance_agency_desc", ""),
            street_name=r.get("reg_street_name", ""),
            postal_code=r.get("reg_postal_code", ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class AcraError(RuntimeError):
    """Raised on a non-recoverable API problem (with a user-facing message)."""


def _headers() -> dict:
    key = os.environ.get("DATAGOV_API_KEY")
    return {"x-api-key": key} if key else {}


async def _query(params: dict) -> list[Entity]:
    params = {"resource_id": RESOURCE_ID, "fields": ",".join(_FIELDS), **params}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(BASE_URL, params=params, headers=_headers())
    except httpx.HTTPError as e:
        raise AcraError(f"Could not reach data.gov.sg: {e}") from e

    if resp.status_code == 429:
        raise AcraError(
            "Rate limited by data.gov.sg (4 requests / 10s without a key). "
            "Set DATAGOV_API_KEY to raise the limit, or retry shortly."
        )
    if resp.status_code != 200:
        raise AcraError(f"data.gov.sg returned HTTP {resp.status_code}.")

    body = resp.json()
    if not body.get("success"):
        raise AcraError("data.gov.sg reported an unsuccessful query.")
    records = body.get("result", {}).get("records", [])
    return [Entity.from_record(r) for r in records]


async def lookup_by_uen(uen: str) -> Entity | None:
    """Exact-match lookup by UEN. Returns one Entity or None."""
    results = await _query({"filters": json.dumps({"uen": uen.strip().upper()})})
    return results[0] if results else None


async def search_by_name(name: str, limit: int = 10) -> list[Entity]:
    """Free-text search by entity name. Returns up to `limit` matches."""
    limit = max(1, min(limit, 50))
    return await _query({"q": name.strip(), "limit": limit})
