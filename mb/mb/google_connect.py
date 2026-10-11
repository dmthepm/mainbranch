"""``mb connect google --oauth``: the one-time Google sign-in for a business repo.

Read-only Search Console and GA4. A person runs this, never an agent: it opens
a browser (or, with ``--paste``, reads the redirect URL from a real terminal),
receives the authorization code on ``http://127.0.0.1:<port>``, exchanges it
with PKCE and stores the grant. Its last step checks the grant with one
read-only call per granted product, as ``mb connect test google`` does
(``mb/google_probe.py``). ``read_minted_token`` (end of this module) is the
read side: it mints a short-lived access token from the grant for
``read_token``.

Storage (one credential-store item per slot, refs from ``_secret_ref``):

1. ``oauth_grant``: JSON ``client_id``, ``client_secret`` (when the client has
   one), ``refresh_token`` and ``refresh_token_expires_in`` (when returned).
2. ``access_token``: the token from the exchange, as a placeholder that keeps
   ``stored``, ``list`` and ``identity`` working. It is never refreshed.
3. The repo metadata (``.mb/connect.yaml``, and the user-scope file for a
   user-scope entry): refs, ``search_console_site``, ``ga4_property_id``,
   ``oauth_grants``. Readers only follow refs the metadata records, so on a
   first connect nothing is visible until this last write lands.

Every failure carries fixed text; no code, verifier, client secret or token
reaches an exception message, stdout, stderr, JSON or ``repr``.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

from mb import connect as connect_mod
from mb import google_oauth as go
from mb.credential_store import (
    SUPPORTED_BACKENDS,
    CredentialStoreError,
    SecretProbe,
    SecretStore,
    new_credential_deadline,
    select_secret_backend,
)
from mb.durable import atomic_write_text

PROVIDER_ID = "google"
GRANT_SLOT = connect_mod.GOOGLE_OAUTH_GRANT_SLOT
TOKEN_SLOT = "access_token"
CLIENT_JSON_MAX_BYTES = 65536
DEFAULT_TIMEOUT_SECONDS = 300
GRANT_LABEL_NAMES = {"search_console": "Search Console", "ga4": "Analytics (GA4)"}
METADATA_SITE = "search_console_site"
METADATA_PROPERTY = "ga4_property_id"
METADATA_GRANTS = connect_mod.GOOGLE_OAUTH_GRANTS_METADATA

# Matched with `fullmatch`: `$` alone would accept a trailing newline.
_HOST_LABEL_RE = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")
_CLIENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_PROPERTY_RE = re.compile(r"[0-9]{1,20}")

# Test seams. The CLI uses these defaults; tests replace them.
Opener = Callable[[str], bool]
open_browser: Opener = webbrowser.open
token_sender: go.Sender | None = None


class GoogleConnectError(RuntimeError):
    """A bootstrap failure after something may have been written.

    ``state`` is the machine code; ``backend_state`` is set when the credential
    store failed. The message is fixed text that says what is now stored.
    """

    def __init__(
        self, message: str, *, state: str, rule: str = "", backend_state: str = ""
    ) -> None:
        super().__init__(message)
        self.state = state
        self.rule = rule
        self.backend_state = backend_state


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str = field(default="", repr=False)


# --- Inputs ------------------------------------------------------------------


def parse_client_json(text: str) -> OAuthClient:
    """Read a downloaded Desktop-app OAuth client file (``{"installed": {...}}``)."""

    if len(text.encode("utf-8", "replace")) > CLIENT_JSON_MAX_BYTES:
        connect_mod._refuse(
            "oauth_client_malformed",
            "the OAuth client file is too large to be a Google client file. Nothing was "
            "stored. Download the Desktop app client JSON again from the Google Cloud console.",
        )
    try:
        raw = json.loads(text)
    except ValueError:
        raw = None
    if isinstance(raw, dict) and "installed" not in raw and "web" in raw:
        connect_mod._refuse(
            "oauth_client_not_desktop",
            "the OAuth client file is for a Web application client. Nothing was stored. "
            "Create an OAuth client of type Desktop app and download its JSON.",
        )
    section = raw.get("installed") if isinstance(raw, dict) else None
    client_id = section.get("client_id") if isinstance(section, dict) else None
    client_secret = section.get("client_secret", "") if isinstance(section, dict) else None
    if (
        not isinstance(client_id, str)
        or not _CLIENT_ID_RE.fullmatch(client_id)
        or not isinstance(client_secret, str)
    ):
        connect_mod._refuse(
            "oauth_client_malformed",
            "the OAuth client file is not a Google Desktop app client JSON (it needs "
            '"installed" with a "client_id"). Nothing was stored. Download it again from '
            "the Google Cloud console.",
        )
    return OAuthClient(client_id=client_id, client_secret=client_secret)


def read_client_file(path: str) -> str:
    try:
        with open(Path(path).expanduser(), "rb") as handle:
            data = handle.read(CLIENT_JSON_MAX_BYTES + 1)
    except OSError:
        connect_mod._refuse(
            "oauth_client_unreadable",
            "the OAuth client file could not be read. Nothing was stored. Check the path "
            "given to --client-file.",
        )
    return data.decode("utf-8", "replace")


def _valid_host(host: str) -> bool:
    labels = host.split(".")
    return len(labels) >= 2 and all(_HOST_LABEL_RE.fullmatch(label) for label in labels)


def normalize_search_console_site(value: str) -> str:
    """``sc-domain:<host>``, or a URL-prefix property ``http(s)://<host>/...`` ending in ``/``."""

    site = value.strip()
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in site):
        site = ""  # no whitespace or control character anywhere; refused below
    if site.startswith("sc-domain:"):
        host = site.removeprefix("sc-domain:").lower()
        if _valid_host(host):
            return f"sc-domain:{host}"
    else:
        parsed = urllib.parse.urlsplit(site)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and _valid_host(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and "?" not in site
            and "#" not in site
            and parsed.path.startswith("/")
            and site.endswith("/")
        ):
            return site
    connect_mod._refuse(
        "search_console_site_format",
        "search_console_site must be a Search Console property: sc-domain:example.com, or a "
        "URL prefix such as https://www.example.com/ (ending in /). Nothing was stored.",
    )


def normalize_ga4_property_id(value: str) -> str:
    """A numeric GA4 property id; ``properties/123`` becomes ``123``."""

    prop = value.strip().removeprefix("properties/")
    if not _PROPERTY_RE.fullmatch(prop):
        connect_mod._refuse(
            "ga4_property_id_format",
            "ga4_property_id must be the numeric GA4 property id (for example 123456789 or "
            "properties/123456789), not a measurement id (G-...). Nothing was stored.",
        )
    return prop


def normalize_oauth_metadata(given: dict[str, str]) -> dict[str, str]:
    """``given`` with the site and property ids in their checked form (refuses bad ones).

    An empty value (``--metadata search_console_site=``) is kept empty: it
    asks for that key to be removed (see ``merge_oauth_metadata``).
    """

    normalized = dict(given)
    if normalized.get(METADATA_SITE):
        normalized[METADATA_SITE] = normalize_search_console_site(normalized[METADATA_SITE])
    if normalized.get(METADATA_PROPERTY):
        normalized[METADATA_PROPERTY] = normalize_ga4_property_id(normalized[METADATA_PROPERTY])
    return normalized


def merge_oauth_metadata(existing: Any, given: dict[str, str]) -> dict[str, str]:
    """The recorded metadata updated with ``given``: keys given are set, keys
    given with an empty value are removed, every other recorded key is kept."""

    return connect_mod.merge_recorded_metadata(existing, normalize_oauth_metadata(given))


def _oauth_metadata(pairs: list[str], existing: dict[str, Any]) -> dict[str, str]:
    given = connect_mod._parse_metadata(pairs)
    if METADATA_GRANTS in given:
        connect_mod._refuse(
            "oauth_metadata_reserved",
            f"{METADATA_GRANTS} is recorded by the Google sign-in itself and cannot be set "
            "with --metadata. Nothing was stored.",
        )
    return merge_oauth_metadata(existing, given)


# --- Existing connection -----------------------------------------------------


@dataclass
class _Existing:
    entry: dict[str, Any]
    grant: dict[str, str]
    token: dict[str, str]

    @property
    def oauth(self) -> bool:
        return bool(self.grant.get("ref"))

    @property
    def has_access_token(self) -> bool:
        return bool(self.token.get("ref"))


def _slot(entry: dict[str, Any], name: str) -> dict[str, str]:
    raw_secrets = entry.get("secrets")
    secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
    raw = secrets.get(name)
    if not isinstance(raw, dict) or not raw.get("ref"):
        return {}
    return {"ref": str(raw["ref"]), "backend": str(raw.get("backend") or "local-file")}


def _existing_entry(config: dict[str, Any], repo_id: str) -> _Existing:
    raw = config["providers"].get(PROVIDER_ID)
    if not isinstance(raw, dict):
        raw = connect_mod._user_scope_provider_entry(repo_id, PROVIDER_ID)
    entry = raw if isinstance(raw, dict) else {}
    return _Existing(entry=entry, grant=_slot(entry, GRANT_SLOT), token=_slot(entry, TOKEN_SLOT))


def entry_is_oauth(entry: dict[str, Any] | None) -> bool:
    return isinstance(entry, dict) and bool(_slot(entry, GRANT_SLOT))


def _refuse_by_mode(existing: _Existing, *, reauth: bool, replace_access_token: bool) -> None:
    if existing.oauth and not reauth:
        connect_mod._refuse(
            "oauth_use_reauth",
            "this repo already has a Google sign-in. Renew it only when status says "
            "reauth_required, with `mb connect google --oauth --reauth`: each sign-in uses "
            "one of Google's 100 refresh tokens per account and OAuth client, and the oldest "
            "is silently revoked. Nothing was changed.",
        )
    if reauth and not existing.oauth:
        connect_mod._refuse(
            "oauth_reauth_without_grant",
            "there is no Google sign-in to renew in this repo. Run `mb connect google --oauth` "
            "without --reauth. Nothing was changed.",
        )
    if existing.has_access_token and not existing.oauth and not replace_access_token:
        connect_mod._refuse(
            "oauth_replaces_access_token",
            "this replaces the stored Google access token; Drive, Docs and Sheets use of this "
            "connection stops working. Re-run with --replace-access-token to proceed. "
            "Nothing was changed.",
        )


def _refuse_other_backend(existing: _Existing, requested: str | None) -> None:
    """Refuse a credential backend asked for (``MB_CONNECT_SECRET_BACKEND``)
    that differs from the store this connection is recorded in: the renewal
    writes to the recorded store, so the request would be ignored."""

    recorded = existing.grant.get("backend") or existing.token.get("backend")
    if not recorded:
        return
    raw = requested if requested is not None else os.environ.get("MB_CONNECT_SECRET_BACKEND")
    if raw is None or not raw.strip():
        return
    try:
        chosen = select_secret_backend(raw)
    except (ValueError, CredentialStoreError):
        chosen = ""
    if chosen == recorded:
        return
    try:
        # A pre-#959 record names the generic `keyring`, which resolves to the
        # same native store as `auto` or `keyring` do now.
        if chosen and chosen == select_secret_backend(recorded):
            return
    except (ValueError, CredentialStoreError):
        pass
    # A hand-edited config could hold anything; name only a known backend.
    name = recorded if recorded in SUPPORTED_BACKENDS else "the recorded store"
    connect_mod._refuse(
        "oauth_backend_kept",
        f"this repo's Google connection is stored in {name}, and renewing it writes to "
        "that same store, so the credential backend asked for (MB_CONNECT_SECRET_BACKEND) "
        f"would be ignored. Unset it, or set it to {name}. Nothing was changed.",
    )


def _stored_client(existing: _Existing) -> OAuthClient | None:
    """The client recorded in the current grant, for ``--reauth`` without a client file."""

    try:
        probe = SecretStore(existing.grant["backend"]).probe(existing.grant["ref"])
    except (connect_mod.KeychainError, ValueError):
        return None
    if not probe.present:
        return None
    return client_from_grant(probe.value)


def _grant_object(value: str) -> dict[str, Any] | None:
    """The stored grant's JSON object, or None when it is not one.

    A hostile, deeply nested value makes the parser raise ``RecursionError``;
    it reads as unreadable, like any other value that is not a JSON object.
    """

    try:
        raw = json.loads(value)
    except (ValueError, RecursionError):
        return None
    return raw if isinstance(raw, dict) else None


def client_from_grant(value: str) -> OAuthClient | None:
    """The OAuth client in a stored grant's JSON, or None when it cannot be used.

    ``--reauth`` without a client file needs this. ``grant_repair_command``
    builds on it, so status, ``--reauth`` and the mint path judge a grant alike.
    """

    raw = _grant_object(value)
    if raw is None:
        return None
    client_id = raw.get("client_id")
    # A client with no secret is stored with the key omitted; `null` and `""`
    # read the same. Any other non-string value is a damaged grant.
    client_secret = raw.get("client_secret")
    if client_secret is None:
        client_secret = ""
    if not isinstance(client_id, str) or not client_id or not isinstance(client_secret, str):
        return None
    return OAuthClient(client_id=client_id, client_secret=client_secret)


def reauth_command(entry: dict[str, Any]) -> str:
    """The ``--reauth`` that renews this sign-in entry and is not refused.

    Bare ``--reauth`` reads the OAuth client from the stored grant; when that
    grant is gone or cannot be read, the command must carry the client file.
    """

    existing = _Existing(entry=entry, grant=_slot(entry, GRANT_SLOT), token={})
    if existing.oauth and _stored_client(existing) is not None:
        return REAUTH_COMMAND
    return REAUTH_WITH_CLIENT_COMMAND


# --- The sign-in -------------------------------------------------------------


def _stdin_is_tty(stream: TextIO | None) -> bool:
    try:
        return bool((stream if stream is not None else sys.stdin).isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _paste_redirect_uri(port: int) -> str:
    # Nothing listens in paste mode: the browser lands on an unreachable page
    # and the operator copies its URL. Any free-looking port works.
    return go.loopback_redirect_uri(port or 8085)


def _sign_in(
    client: OAuthClient,
    *,
    paste: bool,
    no_browser: bool,
    port: int,
    timeout: float,
    emit: Callable[[str], None],
    opener: Opener,
    stdin: TextIO | None,
    paste_reader: Callable[[str], str] | None,
    sender: go.Sender | None,
) -> go.TokenResponse:
    verifier = go.new_code_verifier()
    state = go.new_state()
    challenge = go.code_challenge(verifier)
    emit("Google sign-in (read-only: Search Console, Analytics)")
    if paste:
        redirect_uri = _paste_redirect_uri(port)
        url = go.build_auth_url(
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            state=state,
        )
        emit("Open this URL in a browser on any machine and allow access:")
        emit(f"  {url}")
        emit(
            "The browser then shows a page that cannot load. Copy that page's whole address "
            "(it starts with http://127.0.0.1) and paste it here. Never paste it into a chat."
        )
        code = go.read_pasted_redirect(state, stdin=stdin, reader=paste_reader)
    else:
        with go.LoopbackReceiver(state, port=port, timeout=timeout) as receiver:
            redirect_uri = receiver.redirect_uri
            url = go.build_auth_url(
                client_id=client.client_id,
                redirect_uri=redirect_uri,
                code_challenge=challenge,
                state=state,
            )
            if no_browser:
                emit(f"Open this URL in a browser that can reach {redirect_uri}:")
                emit(f"  {url}")
            else:
                emit("Opening your browser. If it does not open, visit:")
                emit(f"  {url}")
                # webbrowser, never our own argv subprocess. A failure to open
                # is fine: the URL above is the fallback.
                with suppress(Exception):
                    opener(url)
            minutes = max(1, round(timeout / 60))
            emit(f"Waiting for Google on {redirect_uri} ({minutes} min)...")
            code = receiver.wait()
    return go.exchange_code(
        client_id=client.client_id,
        client_secret=client.client_secret or None,
        code=code,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        sender=sender,
    )


def _expires_on(tokens: go.TokenResponse) -> str:
    """UTC date the refresh token expires, when Google set a time limit on it."""

    seconds = tokens.get("refresh_token_expires_in")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    try:
        return (datetime.now(timezone.utc) + timedelta(seconds=float(seconds))).date().isoformat()
    except OverflowError:
        return ""


def _grant_json(client: OAuthClient, tokens: go.TokenResponse) -> str:
    grant: dict[str, Any] = {"client_id": client.client_id}
    if client.client_secret:
        grant["client_secret"] = client.client_secret
    grant["refresh_token"] = tokens["refresh_token"]
    if "refresh_token_expires_in" in tokens:
        grant["refresh_token_expires_in"] = tokens["refresh_token_expires_in"]
    return json.dumps(grant, separators=(",", ":"), sort_keys=True)


# --- Storage and its honest failure messages ---------------------------------


@dataclass
class _Writes:
    """What has been written so far, for the partial-failure message."""

    fresh: bool  # no OAuth grant was recorded before this run
    replaced_access_token: bool  # an access-token-only entry is being upgraded
    repo: Path | None = None
    scope: str = "repo"
    grant_started: bool = False  # the grant write began; it may have landed
    grant: bool = False
    token: bool = False
    user_scope: bool = False  # the user-scope entry (which readers follow) is written
    metadata: bool = False  # the repo metadata is written: the sign-in is complete


@dataclass
class Progress:
    """Filled in by ``bootstrap`` as it writes, so a caller interrupted part way
    (Ctrl-C) can say exactly what is stored."""

    writes: _Writes | None = None


def _recovery_command(writes: _Writes, command: str, *, fresh: bool = False) -> str:
    if fresh:
        command += f" --scope {writes.scope}"
        if writes.replaced_access_token:
            command += " --replace-access-token"
    if writes.repo is not None and writes.repo != Path.cwd().resolve():
        command += f" --repo {connect_mod._shell_repo_arg(writes.repo)}"
    return command


_REPLACED_NOTE = (
    " The previously stored Google access token was already replaced by the new "
    "read-only one, so Drive, Docs and Sheets use of this connection has stopped."
)


def _partial_message(
    writes: _Writes,
    failed: str,
    *,
    retry: str = "once the store is healthy",
) -> str:
    if failed == "grant":
        return "Nothing was stored and the repo metadata is unchanged."
    if writes.user_scope:
        # Readers already follow the user-scope entry, and a second `--oauth`
        # would refuse (`oauth_use_reauth`), so point at commands that work.
        hydrate = _recovery_command(writes, "mb connect hydrate")
        renew = _recovery_command(writes, "mb connect google --oauth --reauth")
        message = (
            "The new Google sign-in is stored and recorded in user scope, but this repo's "
            f".mb/connect.yaml was not updated. Run `{hydrate}` to record it here "
            f"(no new sign-in needed), or renew it with `{renew}`."
        )
        return message + (_REPLACED_NOTE if writes.replaced_access_token else "")
    if writes.fresh:
        lead = (
            "The Google grant was written to the credential store but this repo does not "
            "record it, so the connection is not set up; the unrecorded item is unused and "
            "the next sign-in overwrites it."
        )
        if writes.replaced_access_token and writes.token:
            lead += _REPLACED_NOTE
        command = _recovery_command(writes, "mb connect google --oauth", fresh=True)
        return lead + f" Re-run `{command}` {retry}, with the same OAuth client and metadata."
    test = _recovery_command(writes, "mb connect test google")
    next_step = f"Run `{test}`."
    if failed == "token":
        return (
            "The new Google grant is stored and replaced the old one, but the access-token "
            "placeholder and the repo metadata were not updated. The connection uses the new "
            f"grant. {next_step}"
        )
    return (
        "The new Google grant and access token are stored and replaced the old ones, but the "
        "repo metadata was not updated, so the granted products and the site or property it "
        f"shows may be stale. {next_step}"
    )


def wrote_anything(progress: Progress | None) -> bool:
    """Might the credential store hold something from this run?"""

    writes = progress.writes if progress is not None else None
    return writes is not None and (writes.grant or writes.grant_started)


def cancelled_message(progress: Progress | None, lead: str = "Google sign-in cancelled") -> str:
    """What Ctrl-C (or a crash) during ``bootstrap`` left behind, as fixed text."""

    writes = progress.writes if progress is not None else None
    if writes is None or not (writes.grant or writes.grant_started):
        return f"{lead}. Nothing was stored."
    if not writes.grant:
        # Interrupted inside the grant write: it may or may not have landed.
        if writes.fresh:
            command = _recovery_command(writes, "mb connect google --oauth", fresh=True)
            return (
                f"{lead} while the new Google grant was being written, so it may have been "
                "stored. This repo does not record it, so the connection is not set up; an "
                "unrecorded item is unused and the next sign-in overwrites it. Re-run "
                f"`{command}` to finish it, with the same OAuth client and metadata."
            )
        return (
            f"{lead} while the new Google grant was being written, so it may have been "
            "stored. If it was, it replaced the old grant and the connection uses it; run "
            f"`{_recovery_command(writes, 'mb connect test google')}` to check."
        )
    if writes.metadata:
        return (
            f"{lead} after it finished: the new sign-in is stored and recorded. See it with "
            f"`{_recovery_command(writes, 'mb connect status google')}`."
        )
    failed = "token" if not writes.token else "metadata"
    return f"{lead} part way. " + _partial_message(writes, failed, retry="to finish it")


def _store_failure(
    exc: connect_mod.KeychainError, writes: _Writes, failed: str
) -> GoogleConnectError:
    detail = connect_mod._backend_repair(exc.reason)
    return GoogleConnectError(
        f"{detail['summary']} {_partial_message(writes, failed)} {detail['repair']}".strip(),
        state=connect_mod.BACKEND_FAILURE_STATE,
        backend_state=exc.reason,
    )


def _user_scope_record_failed(
    exc: OSError | connect_mod.UserScopeReadOnlyError | connect_mod.ConfigCorruptError,
    store: SecretStore,
    snapshots: list[tuple[str, str, SecretProbe, str]],
    writes: _Writes,
    *,
    reauth: bool,
    account_label: str,
) -> GoogleConnectError:
    """Restore what was stored before, then say why the user-scope record failed.

    Same restore as ``mb connect --scope user``. Shows the true cause and fix with
    ``~/`` paths, never backend text or a credential. ``snapshots`` holds
    ``(label, ref, previous, written)`` for the grant and the access token.
    """

    shown, cause, fix = connect_mod._user_scope_record_failure(exc)
    unrestored = connect_mod._restore_secrets(store, snapshots)
    _minted.pop((store.backend, snapshots[0][1]), None)
    record_state = (
        "The repo metadata is unchanged, but the user-scope record may have changed."
        if isinstance(exc, connect_mod.UserScopeRecordRestoreError)
        else "The repo metadata is unchanged."
    )
    if unrestored:
        command = ["mb", "connect", "google", "--oauth"]
        if reauth:
            command.append("--reauth")
        else:
            command.extend(["--scope", "user"])
        if writes.replaced_access_token:
            command.append("--replace-access-token")
        if account_label:
            command.extend(["--account", account_label])
        repo = writes.repo if writes.repo is not None else Path.cwd().resolve()
        command.extend(["--repo", str(repo)])
        return GoogleConnectError(
            f"The Google sign-in was stored but not recorded: the user-scope connect file "
            f"{shown} {cause}, and the previous credential state could not be restored "
            f"({' and '.join(unrestored)} stayed changed). "
            f"{record_state} {fix} first, then rerun "
            f"`{connect_mod._shell_replay_command(command, repo)}` with the same OAuth "
            "client and metadata.",
            state="metadata_write_failed",
        )
    undone = (
        "The previous Google credentials were restored."
        if not writes.fresh or writes.replaced_access_token
        else "The new sign-in was removed, so nothing was stored."
    )
    return GoogleConnectError(
        f"The Google sign-in was not recorded: the user-scope connect file {shown} "
        f"{cause}. {undone} {record_state} {fix}, then rerun the command.",
        state="metadata_write_failed",
    )


def bootstrap(
    repo: str | Path = ".",
    *,
    client_json: str | None,
    metadata_pairs: list[str] | None = None,
    reauth: bool = False,
    paste: bool = False,
    no_browser: bool = False,
    port: int = 0,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    replace_access_token: bool = False,
    account_label: str = "",
    scope: str = "",
    secret_backend: str | None = None,
    emit: Callable[[str], None] | None = None,
    opener: Opener | None = None,
    sender: go.Sender | None = None,
    stdin: TextIO | None = None,
    paste_reader: Callable[[str], str] | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Run the sign-in and store the grant. Refusals raise ``ConnectRefusal``.

    ``GoogleOAuthError`` (declined, timeout, state mismatch, token endpoint)
    means nothing was stored. ``GoogleConnectError`` means a write failed and
    its message says what is stored now.
    """

    say = emit or (lambda line: print(line, file=sys.stderr))
    provider = connect_mod.normalize_provider(PROVIDER_ID)
    normalized_scope = scope.strip().lower().replace("_", "-") or "repo"
    if normalized_scope not in connect_mod.CONNECT_SCOPES:
        connect_mod._refuse("connect_scope", "--scope must be repo or user. Nothing was changed.")
    target = Path(repo).resolve()
    config = connect_mod._read_config(target)
    repo_id = connect_mod._ensure_repo_id(config, target)
    existing = _existing_entry(config, repo_id)
    # A credential-less entry recorded in user scope (`--metadata` alone); a
    # first sign-in recorded in repo scope leaves nothing in it worth keeping.
    user_metadata_only = str(existing.entry.get("scope") or "repo") == "user" and not (
        existing.oauth or existing.has_access_token
    )
    _refuse_by_mode(existing, reauth=reauth, replace_access_token=replace_access_token)
    raw_metadata = existing.entry.get("metadata")
    metadata = _oauth_metadata(
        list(metadata_pairs or []), raw_metadata if isinstance(raw_metadata, dict) else {}
    )
    if client_json is not None:
        client = parse_client_json(client_json)
    else:
        stored = _stored_client(existing) if reauth else None
        if stored is None:
            connect_mod._refuse(
                "oauth_client_required",
                "pass the OAuth client with --client-file PATH or --client-stdin"
                + (
                    " (the stored grant could not be read, so its client is unknown)"
                    if reauth
                    else ""
                )
                + ". Nothing was changed.",
            )
        client = stored
    if paste and not _stdin_is_tty(stdin):
        raise go.GoogleOAuthError("paste_needs_tty")
    if existing.oauth or existing.has_access_token:
        # Renewing (or replacing) a stored credential keeps its scope and
        # store. An entry with no credential yet (`--metadata` alone) is a
        # first sign-in, so --scope is honoured there.
        recorded_scope = str(existing.entry.get("scope") or "repo")
        if scope.strip() and normalized_scope != recorded_scope:
            connect_mod._refuse(
                "oauth_scope_kept",
                f"this repo's Google connection is recorded in {recorded_scope} scope, and "
                f"renewing it keeps that scope, so --scope {normalized_scope} would be ignored. "
                "Re-run without --scope. Nothing was changed.",
            )
        normalized_scope = recorded_scope
        _refuse_other_backend(existing, secret_backend)
    elif existing.entry and not scope.strip():
        normalized_scope = str(existing.entry.get("scope") or "repo")

    if normalized_scope == "user":
        # Before the sign-in and the grant write: nothing is stored if refused.
        connect_mod._ensure_user_scope_writable()

    tokens = _sign_in(
        client,
        paste=paste,
        no_browser=no_browser,
        port=port,
        timeout=timeout,
        emit=say,
        opener=opener or open_browser,
        stdin=stdin,
        paste_reader=paste_reader,
        sender=sender if sender is not None else token_sender,
    )
    if not tokens.get("refresh_token"):
        raise GoogleConnectError(
            "Google returned no refresh token, so Main Branch could not read later without "
            "another sign-in. Nothing was stored. Check that the OAuth client is a Desktop "
            "app client, then sign in again.",
            state="no_refresh_token",
            rule="oauth_no_refresh_token",
        )
    granted = go.granted_labels(str(tokens.get("scope") or ""))
    if not granted:
        raise GoogleConnectError(
            "The sign-in granted neither Search Console nor Analytics read access. Nothing "
            "was stored. Sign in again and tick both read-only boxes.",
            state="grant_missing",
            rule="oauth_no_scope_granted",
        )
    missing = [label for label in GRANT_LABEL_NAMES if label not in granted]
    metadata[METADATA_GRANTS] = ",".join(granted)

    deadline = new_credential_deadline()
    backend = existing.grant.get("backend") or existing.token.get("backend") or secret_backend
    store = SecretStore(backend)
    grant_ref = connect_mod._secret_ref(repo_id, PROVIDER_ID, GRANT_SLOT)
    token_ref = connect_mod._secret_ref(repo_id, PROVIDER_ID, TOKEN_SLOT)
    writes = _Writes(
        fresh=not existing.oauth,
        replaced_access_token=existing.has_access_token and not existing.oauth,
        repo=target,
        scope=normalized_scope,
    )
    if progress is not None:
        progress.writes = writes
    previous_grant: SecretProbe | None = None
    previous_token: SecretProbe | None = None
    if normalized_scope == "user":
        # Snapshot for the restore if the user-scope record cannot be written. A
        # separate bounded read, taken before anything is stored.
        previous_grant = store.probe(grant_ref, deadline=new_credential_deadline())
        previous_token = store.probe(token_ref, deadline=new_credential_deadline())
        for probe in (previous_grant, previous_token):
            if not probe.backend_ok:
                raise _store_failure(connect_mod.KeychainError(probe.reason), writes, "grant")
    # A token minted earlier in this process came from the grant being replaced.
    _minted.pop((store.backend, grant_ref), None)
    writes.grant_started = True
    try:
        store.set(grant_ref, _grant_json(client, tokens), deadline=deadline)
    except connect_mod.KeychainError as exc:
        raise _store_failure(exc, writes, "grant") from None
    writes.grant = True
    try:
        store.set(token_ref, str(tokens["access_token"]), deadline=deadline)
    except connect_mod.KeychainError as exc:
        raise _store_failure(exc, writes, "token") from None
    writes.token = True

    now = connect_mod._now()
    entry = {
        "provider": provider.id,
        "connected": True,
        "scope": normalized_scope,
        "account_label": account_label.strip() or str(existing.entry.get("account_label") or ""),
        "connected_at": now,
        "last_checked_at": now,
        "auth": provider.auth,
        "secrets": {
            TOKEN_SLOT: {"ref": token_ref, "backend": store.backend},
            GRANT_SLOT: {"ref": grant_ref, "backend": store.backend},
        },
        "metadata": metadata,
    }
    expires_on = _expires_on(tokens)
    if expires_on:
        entry["oauth"] = {"refresh_token_expires_on": expires_on}
    config["providers"][provider.id] = entry
    user_scope_path = ""
    try:
        if normalized_scope == "user":
            try:
                user_scope_path = str(
                    connect_mod._write_user_scope_provider(
                        repo_id,
                        repo_identity=config.get("repo_identity") or {},
                        provider_id=provider.id,
                        entry=entry,
                    )
                )
            except (
                OSError,
                connect_mod.UserScopeReadOnlyError,
                connect_mod.ConfigCorruptError,
            ) as exc:
                assert previous_grant is not None and previous_token is not None
                raise _user_scope_record_failed(
                    exc,
                    store,
                    [
                        (
                            "the Google grant",
                            grant_ref,
                            previous_grant,
                            _grant_json(client, tokens),
                        ),
                        (
                            "the access token",
                            token_ref,
                            previous_token,
                            str(tokens["access_token"]),
                        ),
                    ],
                    writes,
                    reauth=reauth,
                    account_label=account_label,
                ) from None
            writes.user_scope = True
        path = connect_mod._write_config(target, config)
        writes.metadata = True
    except (OSError, ValueError):
        raise GoogleConnectError(
            "The repo metadata could not be written. " + _partial_message(writes, "metadata"),
            state="metadata_write_failed",
        ) from None

    if user_metadata_only and normalized_scope == "repo":
        connect_mod._drop_user_scope_metadata_only(repo_id, provider.id)
    check = _check_after_sign_in(provider, target, str(tokens["access_token"]), deadline)
    status = connect_mod.status_provider(provider.id, target, _credential_deadline=deadline)
    return {
        "ok": not missing and status["state"] not in {"missing_secret", "backend_unavailable"},
        "ready": bool(check["ok"]),
        "provider": provider.id,
        "credential_mode": "oauth",
        "reauth": reauth,
        "oauth_grants": granted,
        "missing_grants": missing,
        "scope": normalized_scope,
        "config_path": str(path),
        "user_scope_path": user_scope_path,
        "credential_backend": store.backend,
        "credential_boundary": store.boundary(),
        "provider_verified": bool(check["ok"]),
        "repair_command": "mb connect google --oauth --reauth" if missing else "",
        "check": check,
        "safe_to_share": True,
        "status": status,
    }


def _check_after_sign_in(
    provider: connect_mod.Provider, target: Path, access_token: str, deadline: float
) -> dict[str, Any]:
    """The sign-in's last step: ``mb connect test google`` with the token just exchanged.

    It reads each granted product once and records the outcome as the test
    would. The sign-in is already stored, so a check that cannot run never
    fails it; the result says what to run next.
    """

    from mb import google_probe

    try:
        return google_probe.test_google(
            provider,
            target,
            source="repo",
            before={},
            status_again=lambda: connect_mod.status_provider(
                provider.id, target, _credential_deadline=deadline
            ),
            access_token=access_token,
            # The sign-in has just written .mb/connect.yaml at the person's
            # request, so its check is recorded there even when git tracks it.
            record_in_tracked_config=True,
        )
    except Exception as exc:  # the sign-in is stored; never let the check undo that
        return {
            "ok": False,
            "provider": provider.id,
            "state": go.STATE_UNVALIDATED,
            "rule": "check_failed",
            "summary": (
                f"The check against Google stopped on an unexpected error ({type(exc).__name__}; "
                "details are hidden because they may hold a secret)."
            ),
            "repair_command": "mb connect test google",
            "recorded": False,
            "needs_action": True,
            "products": {},
            "safe_to_share": True,
        }


def render_result(result: dict[str, Any]) -> None:
    granted = ", ".join(GRANT_LABEL_NAMES[label] for label in result["oauth_grants"])
    print(f"Granted (read-only): {granted}")
    for label in result["missing_grants"]:
        print(
            f"Not granted: {GRANT_LABEL_NAMES[label]}. Its reads will refuse until you sign in "
            "again with `mb connect google --oauth --reauth` and tick its box."
        )
    print(f"Stored: yes ({result['credential_boundary']})")
    print(f"metadata: {result['config_path']}")
    if result.get("user_scope_path"):
        print(f"user scope: {result['user_scope_path']}")
    check = result.get("check") or {}
    if check:
        from mb import google_probe

        verdict = "ok" if check.get("ok") else f"warn ({connect_mod.state_label(check['state'])})"
        print(f"Checked with Google (read-only): {verdict}")
        if check.get("summary"):
            print(f"summary: {check['summary']}")
        google_probe.render_products(check.get("products") or {})
        if check.get("repair_command"):
            print(f"next: {check['repair_command']}")
    print("See it with `mb connect status google`.")


# --- Read-time minting (`mb connect token` / `exec` / `read_token`) ------------

STATE_REAUTH_REQUIRED = go.STATE_REAUTH_REQUIRED
REAUTH_COMMAND = go.REPAIRS[go.STATE_REAUTH_REQUIRED]
# A grant that cannot be read has no client to reuse, so --reauth needs the file.
REAUTH_WITH_CLIENT_COMMAND = f"{REAUTH_COMMAND} --client-file <Desktop client JSON>"
# Reuse a minted token until this many seconds before Google says it expires.
MINT_EXPIRY_MARGIN_SECONDS = 60
# Used when Google's answer carries no usable ``expires_in``.
MINT_DEFAULT_LIFETIME_SECONDS = 3600

_EXPIRES_ON_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True)
class _Mint:
    """One token-endpoint outcome, kept for the rest of this ``mb`` process."""

    ok: bool
    token: str = field(default="", repr=False)
    expires_at: float = 0.0
    state: str = ""
    rule: str = ""
    error: str = ""
    repair_command: str = ""


# Keyed by the grant's (backend, ref). One token call per grant per process:
# a success is reused until it nears expiry, a failure is not retried.
_minted: dict[tuple[str, str], _Mint] = {}
# Test seam for the clock behind the reuse window.
monotonic: Callable[[], float] = time.monotonic


def forget_minted() -> None:
    """Drop every minted token held by this process."""

    _minted.clear()


def _read_result(
    *,
    ok: bool,
    source: str,
    state: str,
    error: str = "",
    repair_command: str = "",
    rule: str = "",
    backend_state: str = "",
    token: str = "",
) -> dict[str, Any]:
    """The ``read_token`` result shape, with ``field`` always ``access_token``."""

    return {
        "ok": ok,
        "provider": PROVIDER_ID,
        "field": TOKEN_SLOT,
        "source": source,
        "token": token,
        "state": state,
        "backend_state": backend_state,
        "error": error,
        "repair_command": repair_command,
        "rule": rule,
    }


@dataclass(frozen=True)
class _Grant:
    """The stored grant, read once per mint. No field shows in ``repr``, so a
    traceback that prints locals (rich ``show_locals``) never shows it."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)


def _grant_fields(value: str) -> _Grant | None:
    """The client id, client secret and refresh token from the stored grant JSON.

    The client is read by ``client_from_grant``, the rule ``--reauth`` uses;
    minting also needs the refresh token.
    """

    client = client_from_grant(value)
    if client is None:
        return None
    raw = _grant_object(value) or {}
    refresh_token = raw.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    return _Grant(client.client_id, client.client_secret, refresh_token)


def grant_repair_command(value: str | None) -> str:
    """The one rule for a stored grant: ``""`` when it can mint an access token.

    Otherwise it names the sign-in that replaces it: bare ``--reauth`` when the
    grant still holds its OAuth client (``--reauth`` reads it from there), and
    ``--reauth --client-file ...`` when the grant is gone (``None``) or its
    client cannot be read. Status, ``mb connect test``, ``token`` and ``exec``
    all name what this returns.
    """

    if value is None or client_from_grant(value) is None:
        return REAUTH_WITH_CLIENT_COMMAND
    if _grant_fields(value) is None:
        return REAUTH_COMMAND
    return ""


def _lifetime(tokens: go.TokenResponse) -> float:
    value = tokens.get("expires_in")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return MINT_DEFAULT_LIFETIME_SECONDS
    return float(value)


# OAuth refusals of the refresh grant other than `invalid_grant`, by the
# `error` code: (rule, fixed text). Anything else gets the generic pair.
_TOKEN_REFUSALS: dict[str, tuple[str, str]] = {
    "invalid_client": (
        "oauth_client_rejected",
        "Google refused the OAuth client recorded in the sign-in (deleted, or its secret "
        "changed); sign in again with the current client file",
    ),
    "unauthorized_client": (
        "oauth_client_unauthorized",
        "Google says the OAuth client recorded in the sign-in may not use this grant "
        "(unauthorized_client); check that it is a Desktop app client, then sign in again "
        "with it",
    ),
    "invalid_scope": (
        "oauth_scope_rejected",
        "Google refused the read-only scopes recorded in the sign-in (invalid_scope); sign in "
        "again with the current client file",
    ),
}
# Any other refusal (`invalid_request` or a code mb does not know) is not about
# the grant or the client, so it is not recorded and names no new sign-in.
_TOKEN_REFUSAL_OTHER = (
    "token_request_rejected",
    "Google's token endpoint refused the refresh request; nothing about the sign-in is "
    "known to be wrong. No access token was minted; try again later",
)


def _mint(grant: _Grant) -> _Mint:
    try:
        tokens = go.refresh_access_token(
            client_id=grant.client_id,
            client_secret=grant.client_secret or None,
            refresh_token=grant.refresh_token,
            sender=token_sender,
        )
    except go.GoogleOAuthError as exc:
        if exc.state == STATE_REAUTH_REQUIRED:
            return _Mint(
                ok=False,
                state=STATE_REAUTH_REQUIRED,
                rule=STATE_REAUTH_REQUIRED,
                error=(
                    "the Google sign-in has expired or was revoked (reauth_required); a person "
                    "must sign in again"
                ),
                repair_command=REAUTH_COMMAND,
            )
        if exc.state == go.STATE_INVALID:
            # Matched against fixed codes only; the code Google sent is never shown.
            code = str(exc.upstream.get("error_code") or "")
            if code not in _TOKEN_REFUSALS:
                rule, error = _TOKEN_REFUSAL_OTHER
                return _Mint(ok=False, state=go.STATE_UNVALIDATED, rule=rule, error=error)
            rule, error = _TOKEN_REFUSALS[code]
            return _Mint(
                ok=False,
                state=go.STATE_INVALID,
                rule=rule,
                error=error,
                repair_command=REAUTH_WITH_CLIENT_COMMAND,
            )
        # Unreachable, a server error or an unreadable answer: nothing about
        # the sign-in is known to be wrong, so nothing is recorded.
        return _Mint(
            ok=False,
            state=go.STATE_UNVALIDATED,
            rule=exc.rule,
            error=f"{exc} No access token was minted; try again later",
        )
    except (OSError, ValueError, http.client.HTTPException):
        # A transport that raised instead of answering. Its text is never shown.
        return _Mint(
            ok=False,
            state=go.STATE_UNVALIDATED,
            rule="token_unreachable",
            error=(
                "Google's token endpoint could not be reached. No access token was minted; "
                "try again later"
            ),
        )
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return _Mint(
            ok=False,
            state=go.STATE_UNVALIDATED,
            rule="token_response_malformed",
            error="Google's token endpoint returned an unreadable response; try again later",
        )
    reuse_for = max(0.0, _lifetime(tokens) - MINT_EXPIRY_MARGIN_SECONDS)
    return _Mint(ok=True, token=access_token, expires_at=monotonic() + reuse_for)


def _record_read_state(target: Path, grant_ref: str, *, reauth_required: bool) -> tuple[str, str]:
    """Record (or clear) ``reauth_required`` so status shows it without calling Google.

    Best effort, and only when it changes: a read never fails because the
    metadata could not be written. Only the entry still holding ``grant_ref``
    is touched. When the user-scope file cannot be written (a full disk, an I/O
    error, a read-only file) or cannot be read (unreadable or invalid YAML), the
    repo metadata is put back as it was and this returns ``(reason, note)``: the
    rule (``user_scope_read_only`` or ``user_scope_write_failed``) and a
    sanitized note saying the state was not recorded (and, if that put-back
    also fails, that ``.mb/connect.yaml`` still shows the check); otherwise
    ``("", "")``.
    """

    reason = ""
    note = ""
    with suppress(OSError, ValueError):
        config = connect_mod._read_config(target)
        repo_id = str(config.get("repo_id") or connect_mod._repo_identity(target)["repo_id"])
        repo_entry = config["providers"].get(PROVIDER_ID)
        entry = (
            repo_entry
            if isinstance(repo_entry, dict)
            else connect_mod._user_scope_provider_entry(repo_id, PROVIDER_ID)
        )
        if not isinstance(entry, dict) or _slot(entry, GRANT_SLOT).get("ref") != grant_ref:
            return "", ""
        raw_previous = entry.get("validation")
        previous: dict[str, Any] = raw_previous if isinstance(raw_previous, dict) else {}
        recorded = previous.get("state") == STATE_REAUTH_REQUIRED
        if recorded == reauth_required:
            return "", ""
        validation: dict[str, Any] = {
            "state": STATE_REAUTH_REQUIRED if reauth_required else "unvalidated",
            "checked_at": connect_mod._now(),
            "provider_verified": False,
            "verified_at": connect_mod._verified_at(previous),
            "summary": "",
            "safe_to_share": True,
        }
        if reauth_required:
            validation["summary"] = (
                "Google refused the stored sign-in (expired or revoked); a person must sign in "
                "again."
            )
            validation["repair"] = f"Run `{REAUTH_COMMAND}` in a terminal (a person, not an agent)."
            validation["repair_command"] = REAUTH_COMMAND
            validation["rule"] = STATE_REAUTH_REQUIRED
        entry["validation"] = validation
        config_path = connect_mod._checked_config_path(target)
        previous_config: bytes | None = None
        if isinstance(repo_entry, dict) and not connect_mod.config_tracked_by_git(target):
            # A tracked .mb/connect.yaml is left as it is; the read itself
            # still reports reauth_required with its repair.
            previous_config = config_path.read_bytes() if config_path.exists() else None
            connect_mod._write_config(target, config)
        if entry.get("scope") == "user" or not isinstance(repo_entry, dict):
            try:
                stored = connect_mod._read_user_scope()["repos"].get(repo_id)
                identity = stored.get("repo_identity") if isinstance(stored, dict) else None
                connect_mod._write_user_scope_provider(
                    repo_id,
                    repo_identity=identity
                    if isinstance(identity, dict)
                    else config.get("repo_identity") or {},
                    provider_id=PROVIDER_ID,
                    entry=entry,
                )
            except (
                OSError,
                connect_mod.UserScopeReadOnlyError,
                connect_mod.ConfigCorruptError,
            ) as exc:
                # All or nothing: the repo metadata goes back as it was.
                reason = (
                    "user_scope_read_only"
                    if isinstance(exc, connect_mod.UserScopeReadOnlyError)
                    else "user_scope_write_failed"
                )
                note = connect_mod._user_scope_not_recorded_detail(exc)
                if previous_config is not None:
                    try:
                        atomic_write_text(config_path, previous_config.decode("utf-8"))
                    except OSError:
                        note += (
                            "; .mb/connect.yaml could not be put back either, so it "
                            "still shows this check"
                        )
    return reason, note


def read_minted_token(entry: dict[str, Any], *, source: str, target: Path) -> dict[str, Any]:
    """``read_token`` for an OAuth-mode ``google`` entry: mint an access token in memory.

    The grant is read once from the credential store and sent only to Google's
    token endpoint. The refresh token and client secret never leave this
    function; only the short-lived access token is returned. Nothing minted is
    written back to the store.
    """

    grant = _slot(entry, GRANT_SLOT)
    backend, ref = grant["backend"], grant["ref"]
    probe = connect_mod._probe_secret_ref(backend, ref)
    if not probe.backend_ok:
        detail = connect_mod._backend_repair(probe.reason)
        error = detail["summary"]
        if probe.reason == "keychain_prompt_pending":
            error = "Google credential: keychain prompt pending"
        return _read_result(
            ok=False,
            source=source,
            state=connect_mod.BACKEND_FAILURE_STATE,
            backend_state=probe.reason,
            error=error,
            repair_command=detail["repair_command"],
        )
    if not probe.present:
        return _read_result(
            ok=False,
            source=source,
            state="missing_secret",
            backend_state="ready",
            rule="oauth_grant_missing",
            error="the Google sign-in grant is missing from the secret store",
            repair_command=REAUTH_WITH_CLIENT_COMMAND,
        )
    fields = _grant_fields(probe.value)
    if fields is None:
        return _read_result(
            ok=False,
            source=source,
            state=go.STATE_INVALID,
            backend_state="ready",
            rule="oauth_grant_malformed",
            error=(
                "the stored Google sign-in grant is unreadable or incomplete; a person must "
                "sign in again"
            ),
            repair_command=grant_repair_command(probe.value),
        )
    key = (backend, ref)
    mint = _minted.get(key)
    reason = ""
    note = ""
    if mint is None or (mint.ok and monotonic() >= mint.expires_at):
        mint = _mint(fields)
        _minted[key] = mint
        if mint.ok or mint.state == STATE_REAUTH_REQUIRED:
            reason, note = _record_read_state(target, ref, reauth_required=not mint.ok)
    if not mint.ok:
        result = _read_result(
            ok=False,
            source=source,
            state=mint.state,
            backend_state="ready",
            rule=mint.rule,
            error=mint.error,
            repair_command=mint.repair_command,
        )
    else:
        result = _read_result(
            ok=True, source=source, state="ready", backend_state="ready", token=mint.token
        )
    if note:
        # Only present when the write-back failed; the read itself is unchanged.
        result["not_recorded_note"] = note
        result["not_recorded_reason"] = reason
    return result


def refresh_token_expires_on(entry: dict[str, Any]) -> str:
    """The coarse date (UTC) the recorded sign-in says its refresh token expires, or ""."""

    raw = entry.get("oauth")
    value = raw.get("refresh_token_expires_on") if isinstance(raw, dict) else None
    return value if isinstance(value, str) and _EXPIRES_ON_RE.fullmatch(value) else ""
