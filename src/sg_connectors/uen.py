"""UEN (Unique Entity Number) format validation for Singapore entities.

Three official issuance formats (per uen.gov.sg). The trailing check letter is
computed by an undisclosed ACRA algorithm — there is no public checksum spec, so
this validates *shape only*. Existence is confirmed by a dataset hit, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (A) Businesses (sole-props / partnerships, ROB): 8 digits + check letter.
_FMT_A = re.compile(r"^\d{8}[A-Z]$")
# (B) Local companies (ROC): yyyy + 5-digit sequence + check letter.
_FMT_B = re.compile(r"^\d{9}[A-Z]$")
# (C) Other entities: prefix(T/S/R) + yy + 2-letter type + 4-digit seq + check letter.
_FMT_C = re.compile(r"^[TSR]\d{2}[A-Z]{2}\d{4}[A-Z]$")


@dataclass
class UenCheck:
    uen: str
    valid: bool
    format: str | None  # "A" | "B" | "C" | None
    description: str


def validate_uen(raw: str) -> UenCheck:
    """Validate a UEN's format. Returns the matched format and a plain-language note.

    Does NOT confirm the entity exists or that the check letter is correct — only
    that the string matches one of the three official UEN shapes.
    """
    uen = (raw or "").strip().upper()

    if _FMT_A.match(uen):
        return UenCheck(
            uen, True, "A",
            "Business (sole-proprietor / partnership), registered with ACRA. "
            "Format: 8 digits + check letter (nnnnnnnnX).",
        )
    if _FMT_B.match(uen):
        year = uen[:4]
        return UenCheck(
            uen, True, "B",
            f"Local company incorporated {year}. "
            "Format: year + 5-digit sequence + check letter (yyyynnnnnX).",
        )
    if _FMT_C.match(uen):
        year = "20" + uen[1:3]
        type_code = uen[3:5]
        return UenCheck(
            uen, True, "C",
            f"Other entity (type code '{type_code}', issued ~{year}). "
            "Format: prefix(T/S/R) + year + 2-letter type + 4-digit sequence + "
            "check letter (TyyPQnnnnX).",
        )

    return UenCheck(
        uen, False, None,
        "Does not match any official UEN format. Expected one of: nnnnnnnnX "
        "(business), yyyynnnnnX (local company), or TyyPQnnnnX (other entity).",
    )
