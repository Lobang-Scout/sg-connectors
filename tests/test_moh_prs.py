"""MOH PRS client tests — network is mocked; no live calls.

The control-query contract is the point of this module, so most of these tests are
about what happens when the register misbehaves rather than when it works.
"""

import httpx
import pytest

from sg_connectors import moh_prs

CONTROL_PLACE, CONTROL_REG = moh_prs.CONTROLS["TCM"]

_HIT = """<html><body>
  Displaying 1 - 1 of 1 records
  <a>NIE XIN ({reg})</a>
</body></html>"""

_MANY = """<html><body>
  Displaying 1 - 2 of 2 records
  <a>CHOO YOKE LENG (T0100394H)</a>
  <a>LEE CHOON TIAM (T0100406E)</a>
</body></html>"""

_NIL = "<html><body> No records found. </body></html>"

# The dangerous one: a page shell with no marker at all. Historically indistinguishable
# from a genuine nil, which is exactly the bug this client refuses to reproduce.
_SHELL = "<html><body> Professionals Search Traditional Chinese Medicine Board </body></html>"


def _client(responder):
    """Build an AsyncClient whose POSTs are answered by `responder(place) -> html`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html>form</html>")
        body = request.content.decode()
        place = ""
        for part in body.split("&"):
            if part.startswith("psearchParamVO.pracPlaceName="):
                from urllib.parse import unquote_plus

                place = unquote_plus(part.split("=", 1)[1])
        return httpx.Response(200, text=responder(place))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_returns_practitioners_on_hit():
    async with _client(lambda p: _MANY) as c:
        res = await moh_prs.search_by_place("TUI NA", client=c)
    assert res.found
    assert [p.registration_no for p in res.practitioners] == ["T0100394H", "T0100406E"]
    assert res.control_verified is True  # a hit is self-validating


async def test_hit_does_not_spend_a_control_query():
    """A non-nil result must not trigger a control — that is the whole cost argument."""
    seen: list[str] = []

    def responder(place):
        seen.append(place)
        return _MANY

    async with _client(responder) as c:
        await moh_prs.search_by_place("TUI NA", client=c)
    assert seen == ["TUI NA"], "a hit must not fire the control query"


async def test_nil_is_verified_by_control_then_returned():
    seen: list[str] = []

    def responder(place):
        seen.append(place)
        return _HIT.format(reg=CONTROL_REG) if place == CONTROL_PLACE else _NIL

    async with _client(responder) as c:
        res = await moh_prs.search_by_place("XIAO HONG ZHONG YI TUI NA", client=c)

    assert res.found is False
    assert res.control_verified is True
    assert seen == ["XIAO HONG ZHONG YI TUI NA", CONTROL_PLACE]


async def test_nil_raises_when_control_does_not_return_its_record():
    """A nil the control cannot vouch for must never be handed back as an absence."""

    def responder(place):
        return _NIL  # even the control comes back empty -> register is degraded

    async with _client(responder) as c:
        with pytest.raises(moh_prs.PrsControlFailed):
            await moh_prs.search_by_place("XIAO HONG", client=c)


async def test_missing_marker_raises_rather_than_reading_as_nil():
    """The regression this client exists to prevent."""
    async with _client(lambda p: _SHELL) as c:
        with pytest.raises(moh_prs.PrsUnreadableResponse):
            await moh_prs.search_by_place("ANYTHING", client=c)


async def test_control_failure_is_not_a_subclass_of_unreadable():
    """The two failures mean different things and must stay distinguishable."""
    assert not issubclass(moh_prs.PrsControlFailed, moh_prs.PrsUnreadableResponse)
    assert issubclass(moh_prs.PrsControlFailed, moh_prs.PrsError)
    assert issubclass(moh_prs.PrsUnreadableResponse, moh_prs.PrsError)


async def test_board_without_a_control_reports_unverified_rather_than_claiming_it():
    def responder(place):
        return _NIL

    async with _client(responder) as c:
        res = await moh_prs.search_by_place("SOMEWHERE", board="DENTIST", client=c)
    assert res.found is False
    assert res.control_verified is False, "must not claim verification it did not do"


async def test_caveat_is_present_on_every_result():
    async with _client(lambda p: _MANY) as c:
        res = await moh_prs.search_by_place("TUI NA", client=c)
    assert "PRIMARY place of practice" in res.to_dict()["caveat"]
    assert "not proof" in res.to_dict()["caveat"]


async def test_language_must_be_valid():
    with pytest.raises(ValueError):
        await moh_prs.search_by_place("X", language="klingon")


async def test_empty_place_rejected():
    with pytest.raises(ValueError):
        await moh_prs.search_by_place("   ")


async def test_http_error_status_raises_prs_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="<html>form</html>")
        return httpx.Response(503, text="down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(moh_prs.PrsError):
            await moh_prs.search_by_place("X", client=c)


async def test_duplicate_registrations_are_deduped():
    dup = """<html><body> Displaying 1 - 2 of 2 records
        <a>NIE XIN (T0101418D)</a><a>NIE XIN (T0101418D)</a></body></html>"""
    async with _client(lambda p: dup) as c:
        res = await moh_prs.search_by_place("D&N", client=c)
    assert len(res.practitioners) == 1
