"""Address-level sweep over the ACRA "Information on Corporate Entities" dataset.

Answers a question `acra.py` cannot: **every entity ever registered at an address**,
live or dead, with unit number, status, dates and SSIC. That history is what turns
"does this business exist" into "what has happened at this premises" — a churn of
short-lived entities at one shop unit reads very differently from a single long
tenancy, and neither is visible from a UEN lookup.

Why a separate module: `acra.py` reads the consolidated "Entities Registered with
ACRA" dataset, which carries only street name and postal code. It cannot distinguish
#01-886 from #01-882. This module reads **collection 2**, which carries block, level,
unit and SSIC.

**Cost, stated plainly.** Collection 2 is sharded alphabetically by entity name across
27 datasets, and an address sweep cannot know which letters it needs. One sweep is
therefore ~27 requests. data.gov.sg allows 4 requests / 10s unauthenticated, so expect
roughly 70 seconds; set DATAGOV_API_KEY to lift it. `shard_ids()` results are cached
per process.

**Honest scope.** Still a MONTHLY snapshot, and still no officer names, no capital and
no financials — those are paywalled at ACRA regardless of dataset. `no_of_officers` is
a count only.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass

import httpx

DATASTORE = "https://data.gov.sg/api/action/datastore_search"
COLLECTION_META = (
    "https://api-production.data.gov.sg/v2/public/api/collections/2/metadata"
)

_FIELDS = [
    "uen",
    "entity_name",
    "entity_type_description",
    "entity_status_description",
    "registration_incorporation_date",
    "block",
    "street_name",
    "level_no",
    "unit_no",
    "building_name",
    "postal_code",
    "primary_ssic_code",
    "primary_ssic_description",
    "no_of_officers",
]

_shard_cache: list[str] = []


class AcraAddressError(RuntimeError):
    """Non-recoverable problem reading the ACRA address dataset."""


@dataclass
class AddressEntity:
    uen: str
    entity_name: str
    entity_type: str
    status: str
    registration_date: str
    block: str
    street_name: str
    unit: str
    building_name: str
    postal_code: str
    ssic_code: str
    ssic_description: str
    officer_count: str

    @classmethod
    def from_record(cls, r: dict) -> "AddressEntity":
        level, unit = r.get("level_no", ""), r.get("unit_no", "")
        return cls(
            uen=r.get("uen", ""),
            entity_name=r.get("entity_name", ""),
            entity_type=r.get("entity_type_description", ""),
            status=r.get("entity_status_description", ""),
            registration_date=r.get("registration_incorporation_date", ""),
            block=r.get("block", ""),
            street_name=r.get("street_name", ""),
            unit=f"#{level}-{unit}" if level not in ("", "na") else "",
            building_name=r.get("building_name", ""),
            postal_code=r.get("postal_code", ""),
            ssic_code=r.get("primary_ssic_code", ""),
            ssic_description=r.get("primary_ssic_description", ""),
            officer_count=r.get("no_of_officers", ""),
        )

    @property
    def is_live(self) -> bool:
        return self.status.lower().startswith("live")

    def to_dict(self) -> dict:
        return asdict(self)


def _headers() -> dict:
    key = os.environ.get("DATAGOV_API_KEY")
    return {"x-api-key": key} if key else {}


async def shard_ids(client: httpx.AsyncClient | None = None) -> list[str]:
    """The 27 collection-2 shard ids (A-Z + Others). Cached per process."""
    if _shard_cache:
        return list(_shard_cache)
    own = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        resp = await client.get(COLLECTION_META, headers=_headers())
        if resp.status_code != 200:
            raise AcraAddressError(
                f"Could not read collection metadata (HTTP {resp.status_code})."
            )
        ids = (
            resp.json()
            .get("data", {})
            .get("collectionMetadata", {})
            .get("childDatasets", [])
        )
        if not ids:
            raise AcraAddressError("Collection metadata carried no childDatasets.")
        _shard_cache.extend(ids)
        return list(ids)
    except httpx.HTTPError as e:
        raise AcraAddressError(f"Could not reach data.gov.sg: {e}") from e
    finally:
        if own:
            await client.aclose()


async def _query_shard(
    client: httpx.AsyncClient, shard: str, postal_code: str, limit: int
) -> list[AddressEntity]:
    params = {
        "resource_id": shard,
        "fields": ",".join(_FIELDS),
        "filters": json.dumps({"postal_code": postal_code}),
        "limit": limit,
    }
    resp = await client.get(DATASTORE, params=params, headers=_headers())
    if resp.status_code == 429:
        raise AcraAddressError(
            "Rate limited by data.gov.sg (4 requests / 10s without a key). "
            "Set DATAGOV_API_KEY, or retry shortly."
        )
    if resp.status_code != 200:
        raise AcraAddressError(f"data.gov.sg returned HTTP {resp.status_code}.")
    body = resp.json()
    if not body.get("success"):
        raise AcraAddressError("data.gov.sg reported an unsuccessful query.")
    return [
        AddressEntity.from_record(r) for r in body.get("result", {}).get("records", [])
    ]


async def sweep_address(
    postal_code: str,
    unit: str | None = None,
    *,
    limit_per_shard: int = 200,
    client: httpx.AsyncClient | None = None,
) -> list[AddressEntity]:
    """Every entity ever registered at `postal_code`, oldest registration first.

    `unit` optionally narrows the result. Give the full "#01-886" form to match one
    premises: level AND unit are both matched, because #01-886 and #10-886 are
    different shops. Giving a bare "886" matches that unit number on EVERY level,
    which is almost never what you want in an HDB block — pass the level.

    Returns dead entities too — that is the point. Cancelled, Struck Off and
    Ceased Registration rows are what reveal churn at a premises.
    """
    postal_code = postal_code.strip()
    if not postal_code.isdigit() or len(postal_code) != 6:
        raise ValueError("postal_code must be a 6-digit Singapore postal code")

    own = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        shards = await shard_ids(client)
        results: list[AddressEntity] = []
        # Sequential on purpose: data.gov.sg rate-limits hard, and a burst of 27
        # concurrent requests reliably trips it.
        for shard in shards:
            results.extend(
                await _query_shard(client, shard, postal_code, limit_per_shard)
            )
            if not os.environ.get("DATAGOV_API_KEY"):
                await asyncio.sleep(2.6)  # stay under 4 req / 10s
    finally:
        if own:
            await client.aclose()

    if unit:
        spec = unit.strip().lstrip("#")
        if "-" in spec:
            # "01-886" -> one premises. Both halves must match; #10-886 is a different shop.
            want_level, want_unit = (p.strip() for p in spec.split("-", 1))
            results = [e for e in results if e.unit == f"#{want_level}-{want_unit}"]
        else:
            # bare "886" -> that unit number on every level. Rarely intended; see docstring.
            results = [e for e in results if e.unit.split("-")[-1] == spec]

    return sorted(results, key=lambda e: (e.registration_date or "", e.entity_name))
