"""Address-sweep tests — network is mocked; no live calls."""

import httpx
import pytest

from sg_connectors import acra_address


def _rec(uen, name, unit, status, date, ssic="86202"):
    level, no = unit.lstrip("#").split("-")
    return {
        "uen": uen,
        "entity_name": name,
        "entity_type_description": "Sole Proprietorship/ Partnership",
        "entity_status_description": status,
        "registration_incorporation_date": date,
        "block": "46",
        "street_name": "JALAN BUKIT HO SWEE",
        "level_no": level,
        "unit_no": no,
        "building_name": "THE BEO CRESCENT",
        "postal_code": "160046",
        "primary_ssic_code": ssic,
        "primary_ssic_description": "na",
        "no_of_officers": "3",
    }


RECORDS = [
    _rec("53498049W", "XIAO HONG", "#01-886", "Live", "2025-02-11"),
    _rec("52901792W", "D&N CHINESE", "#01-886", "Live", "1999-09-14"),
    _rec("53493066B", "AP SPA", "#01-886", "Ceased Registration", "2024-10-11"),
    _rec("53071247D", "XIAOJING BEAUTY", "#01-880", "Cancelled", "2006-06-27"),
]


@pytest.fixture(autouse=True)
def _clear_shard_cache(monkeypatch):
    acra_address._shard_cache.clear()
    monkeypatch.delenv("DATAGOV_API_KEY", raising=False)
    # a key short-circuits the pacing sleep, keeping tests fast
    monkeypatch.setenv("DATAGOV_API_KEY", "test-key")
    yield
    acra_address._shard_cache.clear()


def _client(records, shards=("shard_a", "shard_b")):
    def handler(request: httpx.Request) -> httpx.Response:
        if "collections/2/metadata" in str(request.url):
            return httpx.Response(
                200,
                json={"data": {"collectionMetadata": {"childDatasets": list(shards)}}},
            )
        # only the first shard carries the records; the rest are empty
        shard = request.url.params.get("resource_id")
        payload = records if shard == shards[0] else []
        return httpx.Response(
            200, json={"success": True, "result": {"records": payload}}
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_sweep_returns_all_entities_oldest_first():
    async with _client(RECORDS) as c:
        rows = await acra_address.sweep_address("160046", client=c)
    assert [r.uen for r in rows] == [
        "52901792W",  # 1999
        "53071247D",  # 2006
        "53493066B",  # 2024
        "53498049W",  # 2025
    ]


async def test_sweep_includes_dead_entities():
    """Churn is the signal — cancelled and ceased rows must not be filtered out."""
    async with _client(RECORDS) as c:
        rows = await acra_address.sweep_address("160046", client=c)
    statuses = {r.status for r in rows}
    assert "Cancelled" in statuses and "Ceased Registration" in statuses
    assert sum(1 for r in rows if r.is_live) == 2


async def test_full_unit_form_matches_one_premises_only():
    """#01-886 and #10-886 are different shops. Regression: a live sweep for '886'
    returned #10-886, #03-886, #05-886 and #07-886 alongside the intended #01-886."""
    records = RECORDS + [
        _rec("53139596X", "KO-NEN", "#10-886", "Cancelled", "2009-04-03"),
        _rec("53324144L", "TIAN TIAN TRAVEL", "#03-886", "Live", "2015-12-03"),
    ]
    async with _client(records) as c:
        rows = await acra_address.sweep_address("160046", unit="#01-886", client=c)
    assert {r.uen for r in rows} == {"53498049W", "52901792W", "53493066B"}
    assert all(r.unit == "#01-886" for r in rows)


async def test_bare_unit_number_spans_levels_deliberately():
    """The documented widening: a bare '886' is unit-number-only, across every level."""
    records = RECORDS + [
        _rec("53139596X", "KO-NEN", "#10-886", "Cancelled", "2009-04-03")
    ]
    async with _client(records) as c:
        rows = await acra_address.sweep_address("160046", unit="886", client=c)
    assert {r.unit for r in rows} == {"#01-886", "#10-886"}


async def test_unit_88_does_not_match_886():
    async with _client(RECORDS) as c:
        rows = await acra_address.sweep_address("160046", unit="88", client=c)
    assert rows == []


async def test_unit_filter_is_not_a_prefix_match_on_level():
    """'#1-886' must not match '#01-886' by accident."""
    async with _client(RECORDS) as c:
        rows = await acra_address.sweep_address("160046", unit="#1-886", client=c)
    assert rows == []


async def test_all_shards_are_queried():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "collections/2/metadata" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "collectionMetadata": {
                            "childDatasets": [f"s{i}" for i in range(27)]
                        }
                    }
                },
            )
        seen.append(request.url.params.get("resource_id"))
        return httpx.Response(200, json={"success": True, "result": {"records": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await acra_address.sweep_address("160046", client=c)
    assert len(seen) == 27, "an address sweep must cover every alphabetical shard"


async def test_invalid_postal_code_rejected():
    for bad in ("16004", "1600466", "16004A", ""):
        with pytest.raises(ValueError):
            await acra_address.sweep_address(bad)


async def test_rate_limit_surfaces_actionable_message():
    def handler(request: httpx.Request) -> httpx.Response:
        if "collections/2/metadata" in str(request.url):
            return httpx.Response(
                200, json={"data": {"collectionMetadata": {"childDatasets": ["s0"]}}}
            )
        return httpx.Response(429, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(acra_address.AcraAddressError, match="DATAGOV_API_KEY"):
            await acra_address.sweep_address("160046", client=c)


async def test_no_officer_names_are_ever_produced():
    """Honest scope: the free dataset carries a COUNT, never names."""
    async with _client(RECORDS) as c:
        rows = await acra_address.sweep_address("160046", client=c)
    for row in rows:
        keys = row.to_dict().keys()
        assert "officer_count" in keys
        assert not any("officer_name" in k or "director" in k for k in keys)
