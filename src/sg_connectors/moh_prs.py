"""Client for the MOH Professional Registration System (PRS) public register.

Answers a question no other free Singapore source does: **is a registered healthcare
professional attached to this premises?** The register is searchable by *Name of Place
of Practice*, which is what lets you go from a business to a person.

Source: https://prs.moh.gov.sg — free, no auth. `board` selects the register (TCM,
doctors, dentists, ...) via the site's `hpe` parameter.

Two implementation notes that cost a session to learn:

1. The page is a frameset and the Search button is bound to a JS `resubmit1()` that
   **rewrites the form action** from `showSearchSummaryByName.action` to
   `getSearchSummaryByName.action` before submitting. POST to the latter and no browser
   is needed at all; POST to the former and you get a result-less page shell.
2. That shell is the danger. It renders without any result marker and is easy to mistake
   for a genuine "no records found". See the control-query contract below.

**Control-query contract.** A nil from a scraped register is only trustworthy if the
pipeline is known to be working. This client therefore:

  - asserts a result marker on EVERY response (catches the detectable failure class), and
  - re-runs a known-good control query after ANY nil result, raising rather than
    returning an unverified empty list.

Controls are deliberately NOT run on non-nil results: a response carrying records is
self-validating, so a control there buys no information and doubles the request count
against a host that rate-limits aggressively.

**Honest scope.** The register records a practitioner's *primary* place of practice.
Someone registered elsewhere who also works at a premises will not appear. An empty
result is evidence of absence, never proof of it — `SearchResult.caveat` says so on
every response, and callers must not strip it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import httpx

BASE = "https://prs.moh.gov.sg/prs/internet/profSearch"
FORM_URL = f"{BASE}/showSearchSummaryByName.action"
RESULT_URL = f"{BASE}/getSearchSummaryByName.action"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# A response MUST carry one of these, or the request did not really run.
_MARKER = re.compile(
    r"Displaying\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+records|No records found\."
)
_ROW = re.compile(r"([A-Z][A-Z '\-]{2,48}?)\s*\(([A-Z]\d{7}[A-Z])\)")

# Known-good control per board: a place-of-practice substring and a registration number
# that MUST come back. Chosen to be long-lived, not incidental to any one investigation.
CONTROLS: dict[str, tuple[str, str]] = {
    "TCM": ("D&N", "T0101418D"),
}

CAVEAT = (
    "The register records a practitioner's PRIMARY place of practice. A practitioner "
    "registered elsewhere who also works at this premises will not appear. An empty "
    "result is evidence of absence, not proof of it."
)


class PrsError(RuntimeError):
    """Non-recoverable problem talking to the PRS."""


class PrsUnreadableResponse(PrsError):
    """The response carried no result marker — the search did not actually run.

    This is the failure that silently masquerades as 'no records found'. It is raised,
    never returned, so it can never be mistaken for a negative finding.
    """


class PrsControlFailed(PrsError):
    """A nil result could not be trusted: the control query did not return its record.

    Either the register is degraded or the client is broken. Callers must treat this as
    'unknown', never as 'nobody is registered here'.
    """


@dataclass
class Practitioner:
    name: str
    registration_no: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    place_query: str
    board: str
    practitioners: list[Practitioner] = field(default_factory=list)
    control_verified: bool = False
    caveat: str = CAVEAT

    @property
    def found(self) -> bool:
        return bool(self.practitioners)

    def to_dict(self) -> dict:
        return {
            "place_query": self.place_query,
            "board": self.board,
            "practitioners": [p.to_dict() for p in self.practitioners],
            "count": len(self.practitioners),
            "control_verified": self.control_verified,
            "caveat": self.caveat,
        }


def _strip(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _parse(text: str) -> list[Practitioner]:
    seen: set[str] = set()
    out: list[Practitioner] = []
    for name, reg in _ROW.findall(text):
        if reg in seen:
            continue
        seen.add(reg)
        out.append(Practitioner(name=" ".join(name.split()), registration_no=reg))
    return out


async def _raw_search(
    client: httpx.AsyncClient, place: str, board: str, language: str
) -> list[Practitioner]:
    """One search. Raises PrsUnreadableResponse if the response carries no marker."""
    # Prime the session — the POST is only honoured against an established frameset session.
    await client.get(f"{BASE}/main.action", params={"hpe": board})
    await client.get(FORM_URL)

    form = {
        "hpe": board,
        "regNo": "",
        "psearchParamVO.searchBy": "N",
        "psearchParamVO.name": "",
        "psearchParamVO.pracPlaceName": place,
        "psearchParamVO.regNo": "",
        "psearchParamVO.language": language,
        "istermConditions": "on",
        "selectType": "all",
    }
    try:
        resp = await client.post(
            RESULT_URL,
            data=form,
            headers={"Referer": f"{BASE}/main.action?hpe={board}"},
        )
    except httpx.HTTPError as e:
        raise PrsError(f"Could not reach prs.moh.gov.sg: {e}") from e

    if resp.status_code != 200:
        raise PrsError(f"prs.moh.gov.sg returned HTTP {resp.status_code}.")

    text = _strip(resp.text)
    if not _MARKER.search(text):
        raise PrsUnreadableResponse(
            "PRS returned a page with no result marker, so the search did not run. "
            "This is NOT a 'no records found' result and must not be read as one. "
            "Most often a rate-limit or an interstitial; retry after a pause."
        )
    return _parse(text)


async def search_by_place(
    place: str,
    board: str = "TCM",
    language: str = "eng",
    *,
    client: httpx.AsyncClient | None = None,
) -> SearchResult:
    """Find registered practitioners whose primary place of practice matches `place`.

    Substring match, case-insensitive at the source. `language` must be "chi" to match a
    Chinese place name; the English index will not find it.

    A nil result triggers a control query before it is returned. If the control fails,
    PrsControlFailed is raised rather than an empty result being handed back.
    """
    place = place.strip()
    if not place:
        raise ValueError("place must not be empty")
    if language not in ("eng", "chi"):
        raise ValueError("language must be 'eng' or 'chi'")

    own_client = client is None
    client = client or httpx.AsyncClient(
        headers={"User-Agent": _UA}, follow_redirects=True, timeout=45.0
    )
    try:
        found = await _raw_search(client, place, board, language)
        if found:
            # A non-nil result is self-validating: the pipeline demonstrably worked.
            return SearchResult(place, board, found, control_verified=True)

        control = CONTROLS.get(board)
        if control is None:
            # No control defined for this board — say so rather than implying verification.
            return SearchResult(place, board, [], control_verified=False)

        probe, expected_reg = control
        control_hits = await _raw_search(client, probe, board, "eng")
        if not any(p.registration_no == expected_reg for p in control_hits):
            raise PrsControlFailed(
                f"Nil result for {place!r} could NOT be verified: control query "
                f"{probe!r} did not return {expected_reg}. Treat this as unknown, "
                f"not as an absence of registered practitioners."
            )
        return SearchResult(place, board, [], control_verified=True)
    finally:
        if own_client:
            await client.aclose()
