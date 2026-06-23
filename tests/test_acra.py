"""ACRA client tests — network is mocked; no live calls."""

import json

import httpx
import pytest

import acra

_SAMPLE_RECORD = {
    "uen": "201912345K",
    "entity_name": "ACME WIDGETS PTE. LTD.",
    "entity_type_desc": "Local Company",
    "uen_status_desc": "Registered",
    "uen_issue_date": "2019-03-15",
    "issuance_agency_desc": "ACRA",
    "reg_street_name": "ROBINSON ROAD",
    "reg_postal_code": "068898",
}


def _mock_transport(records, status=200, success=True):
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"success": success, "result": {"records": records}})

    return httpx.MockTransport(handler)


@pytest.fixture
def patch_client(monkeypatch):
    """Patch httpx.AsyncClient to use a mock transport with the given records."""
    def _apply(records, status=200, success=True):
        transport = _mock_transport(records, status, success)
        orig = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return orig(*args, **kwargs)

        monkeypatch.setattr(acra.httpx, "AsyncClient", factory)

    return _apply


def test_entity_from_record_maps_fields():
    e = acra.Entity.from_record(_SAMPLE_RECORD)
    assert e.uen == "201912345K"
    assert e.entity_name == "ACME WIDGETS PTE. LTD."
    assert e.entity_type == "Local Company"
    assert e.status == "Registered"
    assert e.postal_code == "068898"


def test_to_dict_has_no_paywalled_fields():
    e = acra.Entity.from_record(_SAMPLE_RECORD)
    d = e.to_dict()
    # The free dataset never carries these — guard against silently inventing them.
    for paywalled in ("officers", "directors", "shareholders", "paid_up_capital", "ssic"):
        assert paywalled not in d


@pytest.mark.asyncio
async def test_lookup_by_uen_hit(patch_client):
    patch_client([_SAMPLE_RECORD])
    e = await acra.lookup_by_uen("201912345K")
    assert e is not None and e.uen == "201912345K"


@pytest.mark.asyncio
async def test_lookup_by_uen_miss(patch_client):
    patch_client([])
    assert await acra.lookup_by_uen("999999999Z") is None


@pytest.mark.asyncio
async def test_search_by_name_returns_list(patch_client):
    patch_client([_SAMPLE_RECORD, _SAMPLE_RECORD])
    results = await acra.search_by_name("acme")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_limit_is_clamped(patch_client):
    patch_client([_SAMPLE_RECORD])
    # Should not raise; limit > 50 is clamped internally.
    await acra.search_by_name("acme", limit=999)


@pytest.mark.asyncio
async def test_rate_limit_raises_friendly_error(patch_client):
    patch_client([], status=429)
    with pytest.raises(acra.AcraError, match="Rate limited"):
        await acra.lookup_by_uen("201912345K")


@pytest.mark.asyncio
async def test_unsuccessful_body_raises(patch_client):
    patch_client([], success=False)
    with pytest.raises(acra.AcraError):
        await acra.lookup_by_uen("201912345K")
