"""`mb library` command implementations. Registered in :mod:`mb.cli`."""

from __future__ import annotations

import getpass
import sys
from datetime import date
from pathlib import Path

import typer

from mb import library_rights as rights
from mb.library_files import LibraryError, display
from mb.library_store import Library

LIBRARY_HELP = (
    "Know what media a business has, where it is, and whether a use is cleared. "
    "Run from the business folder; no verb takes another folder. Sources are read, "
    "never changed, and must be folders this user cannot write. This guards against "
    "same OS user accidents only: it does not enforce rights at publication, and a "
    "process running as the same OS user can edit the files it keeps."
)

_USE_HELP = f"Use: {', '.join(rights.USES)}."
_PLATFORM_HELP = f"Platform: {', '.join(rights.PLATFORMS)}."
_USES_OPTION = typer.Option(..., "--use", help=f"Repeatable. {_USE_HELP}")
_PLATFORMS_OPTION = typer.Option([], "--platform", help=f"Repeatable. {_PLATFORM_HELP}")
_SIGHTINGS_OPTION = typer.Option(
    [], "--sighting", help="Repeatable source:path to cover. Default: every sighting."
)


def _say(line: str) -> None:
    """The only way library output reaches the terminal: the whole line is written out safe.

    Callers interpolate raw values; nothing here trusts them, so a field cannot
    reach the terminal unescaped by being left out of a list.
    """
    typer.echo(display(line))


def _fail(message: str) -> typer.Exit:
    typer.echo(display(f"mb library: {message}"), err=True)
    return typer.Exit(2)


def _open(*, init: bool = False) -> Library:
    try:
        return Library(Path.cwd(), init=init)
    except LibraryError as exc:
        raise _fail(str(exc)) from exc


def _date(label: str, value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _fail(f"{label} must be a date as YYYY-MM-DD, not {value!r}") from exc


def _window(from_: str, to: str) -> tuple[date, date] | None:
    if not from_ and not to:
        return None
    if not (from_ and to):
        raise _fail("give both --from and --to, or neither (neither means today)")
    start, end = _date("--from", from_), _date("--to", to)
    if end < start:
        raise _fail("--to is before --from")
    return (start, end)


def _has_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def library_source_add_cmd(
    name: str = typer.Argument(..., help="Short name, e.g. studio."),
    folder: str = typer.Argument(
        ..., help="Media folder to read. Refused if this user can write it."
    ),
) -> None:
    """Register a media source. The library only reads it."""
    lib = _open(init=True)
    try:
        path = lib.add_source(name, folder)
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(f"Added source {name}: {path}")
    _say("Next: mb library scan")


def library_scan_cmd(
    verify: bool = typer.Option(
        False, "--verify", help="Re-read every file and compare with the index."
    ),
) -> None:
    """Fingerprint files in every source and list what was skipped, and why."""
    lib = _open()
    try:
        report = lib.scan(verify=verify)
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(
        f"Scanned {len(lib.sources)} source(s): indexed {report.indexed} "
        f"(new {report.new}, changed {report.changed}, removed {report.removed}); "
        f"read {report.hashed} file(s)."
    )
    if verify:
        _say(f"Verify: indexed {report.indexed}, verified {report.hashed}.")
    for sighting in report.mismatched:
        _say(f"  CONTENT CHANGED under the same size and time: {sighting}")
    _say(f"Skipped ({len(report.skipped)}):")
    for item in report.skipped:
        _say(f"  {item.source}:{item.path}  {item.reason}")
    _say(f"Duplicates ({len(report.duplicates)}):")
    for asset, places in sorted(report.duplicates.items()):
        _say(f"  {asset[:12]}…  {', '.join(places)}")
    for name, reason in report.unavailable:
        _say(f"Unavailable: {name}  {reason} (its index entries were kept)")


def library_find_cmd(
    query: str = typer.Argument("", help="Words to look for in paths, tags and creator."),
    kind: str = typer.Option("", "--kind", help="photo, video, audio, document or other."),
    use: str = typer.Option("", "--for", help=f"Only assets cleared for this. {_USE_HELP}"),
    platform: str = typer.Option("", "--platform", help=_PLATFORM_HELP),
    from_: str = typer.Option("", "--from", help="Window start, YYYY-MM-DD."),
    to: str = typer.Option("", "--to", help="Window end, YYYY-MM-DD."),
    any_word: bool = typer.Option(False, "--any", help="Match any word, not all."),
) -> None:
    """Find assets by words. With --for, list only assets with a cleared sighting.

    With --for, a last line counts the matches that are not cleared. --any means
    match any word, not show uncleared assets.
    """
    window = _window(from_, to)
    lib = _open()
    try:
        report = lib.find_report(
            query,
            kind=kind or None,
            use=rights.Use(use, platform or None) if use else None,
            window=window,
            any_word=any_word,
        )
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    for hit in report.hits:
        _say(f"{hit.asset}  {hit.kind}  {hit.size} bytes")
        for sighting in hit.sightings:
            _say(f"  {sighting}")
        if hit.cleared is not None:
            _say(f"  usable at: {', '.join(hit.cleared)}")
    _say(f"{len(report.hits)} asset(s).")
    if report.not_cleared:
        _say(f"{report.not_cleared} more match but are not cleared.")


def library_show_cmd(asset: str = typer.Argument(..., help="Full asset id.")) -> None:
    """Show every sighting, tags, provenance and deals for one asset."""
    lib = _open()
    try:
        view = lib.show(asset)
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(f"{view.asset}  {view.kind}  {view.size} bytes")
    _say("sightings:")
    for sighting in view.sightings:
        _say(f"  {sighting}")
    _say(f"provenance: {view.provenance}")
    _say(f"creator: {view.creator or '-'}")
    _say(f"tags: {', '.join(view.tags) or '-'}")
    _say("deals:")
    for item in view.deals:
        d = item.deal
        until = "perpetual" if d.perpetual else d.to_date
        _say(
            f"  {d.id}  {item.status}  {','.join(d.uses)} on {','.join(d.platforms) or '-'} "
            f"{d.from_date}..{until}  music {d.music}  said by {d.said_by}"
        )
        _say(f"    covers: {', '.join(d.sightings)}")


def library_check_cmd(
    asset: str = typer.Argument(..., help="Full asset id."),
    use: str = typer.Option(..., "--use", help=_USE_HELP),
    platform: str = typer.Option("", "--platform", help=_PLATFORM_HELP),
    from_: str = typer.Option("", "--from", help="Window start, YYYY-MM-DD (default today)."),
    to: str = typer.Option("", "--to", help="Window end, YYYY-MM-DD (default today)."),
) -> None:
    """May we use this? One answer per sighting; exit 1 unless every one is cleared."""
    window = _window(from_, to)
    lib = _open()
    try:
        answers = lib.check(asset, rights.Use(use, platform or None), window)
        deals = {d.id: d for d in (v.deal for v in lib.show(asset).deals)}
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    for answer in answers:
        verdict = answer.verdict
        if verdict.cleared:
            when = deals[verdict.deal_id].approved_at[:10]
            _say(f"{answer.sighting}  CLEARED (deal {verdict.deal_id}, approved {when})")
        else:
            _say(f"{answer.sighting}  NOT CLEARED ({', '.join(verdict.reasons)})")
    raise typer.Exit(0 if all(a.verdict.cleared for a in answers) else 1)


def library_deal_propose_cmd(
    asset: str = typer.Argument(..., help="Full asset id."),
    uses: list[str] = _USES_OPTION,
    platforms: list[str] = _PLATFORMS_OPTION,
    from_: str = typer.Option(..., "--from", help="First day covered, YYYY-MM-DD."),
    to: str = typer.Option("", "--to", help="Last day covered, YYYY-MM-DD."),
    perpetual: bool = typer.Option(False, "--perpetual", help="No end date; say so explicitly."),
    music: str = typer.Option("unknown", "--music", help=f"One of: {', '.join(rights.MUSIC)}."),
    said_by: str = typer.Option(..., "--said-by", help="Who said yes, and how."),
    platform_code: str = typer.Option(
        "", "--platform-code", help="Platform permission code as PLATFORM:EXPIRY, no code itself."
    ),
    evidence_hash: str = typer.Option("", "--evidence-hash", help="SHA-256 of the evidence file."),
    sightings: list[str] = _SIGHTINGS_OPTION,
) -> None:
    """Write a proposed deal. It clears nothing until a person approves it."""
    lib = _open()
    code: tuple[str, date] | None = None
    if platform_code:
        platform, _, expiry = platform_code.partition(":")
        code = (platform, _date("--platform-code expiry", expiry))
    try:
        deal = lib.propose_deal(
            asset,
            uses=tuple(uses),
            platforms=tuple(platforms),
            from_date=_date("--from", from_),
            to_date=_date("--to", to) if to else None,
            perpetual=perpetual,
            music=music,
            said_by=said_by,
            platform_code=code,
            evidence_hash=evidence_hash,
            sightings=list(sightings) or None,
        )
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(f"Proposed deal {deal.id} (inactive). Review the record, then:")
    _say(f"  mb library deal approve {deal.id}")


def library_deal_approve_cmd(
    deal_id: str = typer.Argument(..., help="The deal's short id."),
) -> None:
    """A person at a terminal types the deal id to activate it. A speed bump and audit record."""
    lib = _open()
    if not _has_terminal():
        raise _fail("approving a deal needs a person at a terminal; none is attached")
    typed = typer.prompt(display(f"Type the deal id ({deal_id}) to approve it"))
    try:
        deal = lib.approve_deal(deal_id, typed, has_terminal=True, approver=getpass.getuser())
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(f"Approved deal {deal.id} as {deal.approved_by} at {deal.approved_at}.")


def library_deal_revoke_cmd(
    deal_id: str = typer.Argument(..., help="The deal's short id."),
    reason: str = typer.Option(..., "--reason", help="Why it was withdrawn."),
) -> None:
    """Mark a deal revoked. Lasts as long as the record file does."""
    lib = _open()
    try:
        deal = lib.revoke_deal(deal_id, reason)
    except LibraryError as exc:
        raise _fail(str(exc)) from exc
    _say(f"Revoked deal {deal.id}.")
