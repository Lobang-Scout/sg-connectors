"""`sgverify` — entity-verification primitives from the command line.

The same core the MCP servers wrap, callable without a Claude session so it can be used
from any repo or shell.

    sgverify uen 53498049W
    sgverify sweep 160046 --unit 886
    sgverify prs "D&N" --board TCM
    sgverify prs 小红 --language chi

Every subcommand takes --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import acra, acra_address, moh_prs


def _emit(payload, as_json: bool, human) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        human()


async def _cmd_uen(args) -> int:
    entity = await acra.lookup_by_uen(args.uen)
    if entity is None:
        _emit(
            {"uen": args.uen, "found": False},
            args.json,
            lambda: print(f"No ACRA record for {args.uen}."),
        )
        return 1

    def human():
        d = entity.to_dict()
        width = max(len(k) for k in d)
        for k, v in d.items():
            print(f"  {k.replace('_', ' '):<{width}}  {v}")
        print("\n  Note: monthly snapshot. No officer names, capital or financials —")
        print("  those are paywalled at ACRA (BizFile+ business profile, S$5.50).")

    _emit(entity.to_dict(), args.json, human)
    return 0


async def _cmd_sweep(args) -> int:
    rows = await acra_address.sweep_address(args.postal_code, unit=args.unit)
    payload = {
        "postal_code": args.postal_code,
        "unit": args.unit,
        "count": len(rows),
        "live_count": sum(1 for r in rows if r.is_live),
        "entities": [r.to_dict() for r in rows],
    }

    def human():
        if not rows:
            print(
                f"No entities ever registered at {args.postal_code}"
                + (f" #{args.unit}" if args.unit else "")
                + "."
            )
            return
        scope = f"{args.postal_code}" + (f" unit {args.unit}" if args.unit else "")
        print(
            f"{len(rows)} entities ever registered at {scope} "
            f"({payload['live_count']} live):\n"
        )
        for r in rows:
            live = "LIVE" if r.is_live else r.status
            print(f"  {r.registration_date or '?':<11} {live:<22} {r.entity_name}")
            print(f"  {'':<11} {r.unit or '-':<22} {r.uen}  SSIC {r.ssic_code}")
        print(
            "\n  Dead entities are shown deliberately: churn at one unit is the signal."
        )

    _emit(payload, args.json, human)
    return 0


async def _cmd_prs(args) -> int:
    try:
        result = await moh_prs.search_by_place(
            args.place, board=args.board, language=args.language
        )
    except moh_prs.PrsControlFailed as e:
        print(f"UNVERIFIED: {e}", file=sys.stderr)
        return 2
    except moh_prs.PrsUnreadableResponse as e:
        print(f"INVALID RUN: {e}", file=sys.stderr)
        return 3

    def human():
        if result.found:
            print(
                f"{len(result.practitioners)} registered practitioner(s) with "
                f"place of practice matching {args.place!r}:\n"
            )
            for p in result.practitioners:
                print(f"  {p.name}  ({p.registration_no})")
        else:
            verified = (
                "control query passed" if result.control_verified else "NOT verified"
            )
            print(f"No registered practitioner found for {args.place!r} [{verified}].")
        print(f"\n  {result.caveat}")

    _emit(result.to_dict(), args.json, human)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sgverify",
        description="Singapore entity-verification primitives (ACRA + MOH PRS).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    u = sub.add_parser("uen", help="Look up one entity by UEN (ACRA open data)")
    u.add_argument("uen")
    u.set_defaults(func=_cmd_uen)

    s = sub.add_parser(
        "sweep",
        help="Every entity ever registered at an address (~27 requests, ~70s unauthenticated)",
    )
    s.add_argument("postal_code", help="6-digit Singapore postal code")
    s.add_argument("--unit", help='Narrow to one unit, e.g. 886 or "#01-886"')
    s.set_defaults(func=_cmd_sweep)

    r = sub.add_parser(
        "prs", help="Registered practitioners at a place of practice (MOH)"
    )
    r.add_argument("place", help="Place-of-practice name or substring")
    r.add_argument("--board", default="TCM", help="MOH register (default: TCM)")
    r.add_argument(
        "--language",
        default="eng",
        choices=["eng", "chi"],
        help="Use chi to match a Chinese place name",
    )
    r.set_defaults(func=_cmd_prs)

    for parser in (u, s, r):
        parser.add_argument(
            "--json", action="store_true", help="Machine-readable output"
        )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except (acra.AcraError, acra_address.AcraAddressError, moh_prs.PrsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
