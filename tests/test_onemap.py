"""OneMap client tests — network is mocked; no live calls."""

import httpx
import pytest

from sg_connectors import onemap

_SAMPLE_RESULT = {
    "SEARCHVAL": "1 RAFFLES PLACE",
    "BLK_NO": "1",
    "ROAD_NAME": "RAFFLES PLACE",
    "BUILDING": "ONE RAFFLES PLACE",
    "ADDRESS": "1 RAFFLES PLACE ONE RAFFLES PLACE SINGAPORE 048616",
    "POSTAL": "048616",
    "LATITUDE": "1.28429",
    "LONGITUDE": "103.85157",
    "X": "29314.5",
    "Y": "29654.8",
}


def _mock_transport(results, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json={"found": len(results), "results": results})

    return httpx.MockTransport(handler)


@pytest.fixture
def patch_client(monkeypatch):
    def _apply(results, status=200):
        transport = _mock_transport(results, status)
        orig = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return orig(*args, **kwargs)

        monkeypatch.setattr(onemap.httpx, "AsyncClient", factory)

    return _apply


def test_address_from_record_maps_fields():
    a = onemap.Address.from_record(_SAMPLE_RESULT)
    assert a.postal == "048616"
    assert a.building == "ONE RAFFLES PLACE"
    assert a.latitude == "1.28429"
    assert a.x == "29314.5"


@pytest.mark.asyncio
async def test_search_returns_results(patch_client):
    patch_client([_SAMPLE_RESULT])
    results = await onemap.search("048616")
    assert len(results) == 1 and results[0].postal == "048616"


@pytest.mark.asyncio
async def test_search_empty(patch_client):
    patch_client([])
    assert await onemap.search("nowhere") == []


@pytest.mark.asyncio
async def test_401_gives_token_hint(patch_client):
    patch_client([], status=401)
    with pytest.raises(onemap.OneMapError, match="ONEMAP_TOKEN"):
        await onemap.search("048616")


@pytest.mark.asyncio
async def test_429_rate_limited(patch_client):
    patch_client([], status=429)
    with pytest.raises(onemap.OneMapError, match="Rate limited"):
        await onemap.search("048616")
